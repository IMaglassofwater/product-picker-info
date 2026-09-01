"""Build a non-destructive Phase 11F production preview and review artifacts."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import sys
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _has_chinese(value: object) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in str(value or ""))


class ChineseItem(BaseModel):
    family_id: int
    chinese_name: str
    chinese_description: str


class ChineseBatch(BaseModel):
    items: list[ChineseItem]


CHINESE_PROMPT = """Translate the supplied factual product identities into concise natural Simplified Chinese. For each family_id return exactly one item. chinese_name should be a plain product name, preferably within 25 Chinese characters. chinese_description must answer only 'what is this?' in one concise factual sentence, preferably within 70 Chinese characters. Preserve uncertainty and source facts. Do not add opportunity judgments, recommendations, demand, profitability, suppliers, costs, differentiation, advantages, or invented facts. If the English description is sparse, translate it conservatively rather than guessing."""


def enrich_chinese(dataset: dict, api_key: str, model: str, *, batch_size: int = 20) -> dict:
    """Enrich language after membership persistence; no retry and no membership writes."""
    import db
    from ai_providers import GeminiProvider
    provider = GeminiProvider(api_key, model)
    failures = 0
    generated_names = 0
    generated_descriptions = 0
    items = dataset["items"]
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        payload = {"items": [{
            "family_id": item["family_id"], "english_name": item["canonical_name"],
            "factual_description": item.get("factual_description", "")[:350],
        } for item in batch]}
        allowed = {item["family_id"]: item for item in batch}
        try:
            raw = provider.analyze(payload, CHINESE_PROMPT, ChineseBatch, allow_retry=False)
            translated = ChineseBatch.model_validate_json(raw)
            returned = set()
            for value in translated.items:
                item = allowed.get(value.family_id)
                if not item or value.family_id in returned:
                    continue
                name = value.chinese_name.strip()[:40]
                description = value.chinese_description.strip()[:120]
                if not (_has_chinese(name) and _has_chinese(description)):
                    continue
                if db.update_daily_discovery_item_language(dataset["run_id"], value.family_id, name, description):
                    item["canonical_name_zh"] = name
                    item["factual_description_zh"] = description
                    generated_names += 1
                    generated_descriptions += 1
                    returned.add(value.family_id)
            failures += len(batch) - len(returned)
        except Exception:
            failures += len(batch)
    return {
        "generated_names": generated_names, "generated_descriptions": generated_descriptions,
        "ai_failures": failures, "api_calls": provider.api_calls_sent,
    }


def audit_production() -> dict:
    """Read only the latest observation-bearing completed/partial production run."""
    import db
    with db._connect() as connection:
        run = connection.execute(
            """SELECT r.* FROM pipeline_runs r
               WHERE r.status IN ('COMPLETED','PARTIAL') AND r.finished_at IS NOT NULL
                 AND EXISTS (SELECT 1 FROM product_observations o WHERE o.pipeline_run_id=r.run_id)
               ORDER BY r.finished_at DESC LIMIT 1"""
        ).fetchone()
        if not run:
            raise RuntimeError("No completed observation-bearing production run exists")
        run = dict(run)
        run_id = run["run_id"]
        counts = dict(connection.execute(
            """SELECT
                 COUNT(DISTINCT o.product_id) AS observations,
                 COUNT(DISTINCT CASE WHEN e.eligibility_status='ELIGIBLE' THEN o.product_id END) AS eligible,
                 COUNT(DISTINCT CASE WHEN e.eligibility_status='ELIGIBLE' AND e.concrete_product_status='CONCRETE' THEN o.product_id END) AS concrete,
                 COUNT(DISTINCT CASE WHEN e.eligibility_status='ELIGIBLE' AND e.concrete_product_status='CONCRETE' AND f.status='ACTIVE' THEN f.id END) AS active_families
               FROM product_observations o
               LEFT JOIN product_eligibility e ON e.product_id=o.product_id
               LEFT JOIN product_family_members fm ON fm.product_id=o.product_id
               LEFT JOIN product_families f ON f.id=fm.family_id
               WHERE o.pipeline_run_id=?""", (run_id,)
        ).fetchone())
        source_rows = connection.execute(
            """SELECT o.source_platform, COUNT(DISTINCT o.product_id) AS observed,
                      COUNT(DISTINCT CASE WHEN e.eligibility_status='ELIGIBLE' AND e.concrete_product_status='CONCRETE' AND f.status='ACTIVE' THEN f.id END) AS families
               FROM product_observations o
               LEFT JOIN product_eligibility e ON e.product_id=o.product_id
               LEFT JOIN product_family_members fm ON fm.product_id=o.product_id
               LEFT JOIN product_families f ON f.id=fm.family_id
               WHERE o.pipeline_run_id=? GROUP BY o.source_platform ORDER BY o.source_platform""", (run_id,)
        ).fetchall()
        tables = {row["table_name"] for row in connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        ).fetchall()}
    return {
        "pipeline_run_id": run_id, "run_timestamp": str(run.get("finished_at")),
        "run_status": run.get("status"), **counts,
        "sources": [dict(row) for row in source_rows],
        "phase11f_tables_present_before": {name: name in tables for name in ("daily_discovery_runs", "daily_discovery_items")},
    }


def _today_html(dataset: dict) -> str:
    items = dataset["items"]
    types = Counter(item.get("product_type") for item in items)
    evidence = Counter(item.get("evidence_strength") for item in items)
    cards = []
    for item in items:
        signals = "".join(f"<li>{escape(str(value))}</li>" for value in item.get("evidence_reasons", []))
        feedback = item.get("actual_feedback", [])
        feedback_html = "".join(f"<li>{escape(value['text'])} · {escape(value['source_platform'])}</li>" for value in feedback[:3]) or "<p>暂无可用的用户文字反馈</p>"
        links = " · ".join(f'<a href="{escape(str(value.get("url")), quote=True)}">{escape(str(value.get("source_platform")))}</a>' for value in item.get("source_records", []) if value.get("url"))
        cards.append(f"""<article><div class='actions'>☆ 收藏　🗑 删除 / 隐藏</div>
<h2>{item['display_order']}. {escape(str(item.get('canonical_name_zh') or item['canonical_name']))}</h2>
<div class='english'>{escape(str(item['canonical_name']))}</div>
<p>{escape(str(item.get('factual_description_zh') or item.get('factual_description') or '暂无事实描述'))}</p>
<b>{escape(str(item.get('product_type')))} · {escape(str(item.get('evidence_strength')))}</b>
<h3>市场信号</h3><ul>{signals}</ul><h3>用户反馈</h3>{feedback_html}<p>来源：{links}</p></article>""")
    return f"""<!doctype html><meta charset='utf-8'><title>Product Picker 今日发现预览</title>
<style>body{{font-family:system-ui;max-width:1000px;margin:auto;background:#f5f6f8;padding:24px}}article{{background:white;border:1px solid #ddd;border-radius:12px;padding:18px;margin:14px 0}}.english{{color:#667}}.actions{{float:right;color:#555}}h3{{margin-bottom:4px}}</style>
<h1>今日发现</h1><p>今天发现 {len(items)} 个产品</p>
<p>实物 {types['PHYSICAL_PRODUCT']} · 软件 {types['SOFTWARE_PRODUCT']} · 产品设计 {types['PRODUCT_DESIGN']}</p>
<p>Strong {evidence['STRONG']} · Moderate {evidence['MODERATE']} · Weak {evidence['WEAK']}</p>{''.join(cards)}"""


def build_preview(output_dir: Path, *, enrich: bool = False) -> dict:
    import db
    from daily_discovery import build_daily_discovery, render_wxpusher_chunks, today_renderer_items, wxpusher_family_ids
    from postgres_backend import initialize_evidence_schema

    audit = audit_production()
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "production_audit.json", audit)
    initialize_evidence_schema(db.DATABASE_SETTINGS.database_url)
    dataset = build_daily_discovery(audit["pipeline_run_id"], persist=True)
    if not dataset.get("run_id"):
        raise RuntimeError("Daily Discovery preview persistence failed")
    enrichment = {"generated_names": 0, "generated_descriptions": 0, "ai_failures": 0, "api_calls": 0}
    if enrich:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for --enrich-chinese")
        enrichment = enrich_chinese(dataset, api_key, os.getenv("GEMINI_TRIAGE_MODEL", "gemini-3.5-flash-lite"))
        dataset = db.get_persisted_daily_discovery(daily_run_id=dataset["run_id"])
    return write_preview_artifacts(output_dir, audit, dataset, enrichment)


def write_preview_artifacts(output_dir: Path, audit: dict, dataset: dict, enrichment: dict | None = None) -> dict:
    """Create review files from an already-persisted snapshot without membership writes."""
    from daily_discovery import render_wxpusher_chunks, today_renderer_items, wxpusher_family_ids
    enrichment = enrichment or {"generated_names": 0, "generated_descriptions": 0, "ai_failures": 0, "api_calls": 0}
    today = today_renderer_items(dataset)
    chunks = render_wxpusher_chunks(dataset)
    dataset_ids = [item["family_id"] for item in dataset["items"]]
    today_ids = [item["family_id"] for item in today]
    wx_ids = wxpusher_family_ids(chunks)
    parity = {
        "dataset_count": len(dataset_ids), "today_count": len(today_ids), "wxpusher_count": len(wx_ids),
        "missing_today": sorted(set(dataset_ids)-set(today_ids)), "missing_wxpusher": sorted(set(dataset_ids)-set(wx_ids)),
        "extra_today": sorted(set(today_ids)-set(dataset_ids)), "extra_wxpusher": sorted(set(wx_ids)-set(dataset_ids)),
        "order_mismatches": [index for index, values in enumerate(zip(dataset_ids, today_ids, wx_ids), 1) if len(set(values)) != 1],
        "family_id_parity": dataset_ids == today_ids == wx_ids,
        "order_parity": dataset_ids == today_ids == wx_ids,
    }
    chinese = {
        "total_items": len(dataset["items"]),
        "chinese_names": sum(_has_chinese(item.get("canonical_name_zh")) for item in dataset["items"]),
        "chinese_descriptions": sum(_has_chinese(item.get("factual_description_zh")) for item in dataset["items"]),
    }
    chinese["english_name_fallbacks"] = chinese["total_items"] - chinese["chinese_names"]
    chinese["english_description_fallbacks"] = chinese["total_items"] - chinese["chinese_descriptions"]
    chinese["ai_failures"] = enrichment["ai_failures"]
    chinese["api_calls"] = enrichment["api_calls"]
    for key in ("cache_hits", "deterministic_names", "deterministic_descriptions", "english_only"):
        chinese[key] = enrichment.get(key, 0)
    _write_json(output_dir / "daily_discovery_preview.json", dataset)
    _write_json(output_dir / "parity_report.json", parity)
    _write_json(output_dir / "chinese_quality_report.json", chinese)
    (output_dir / "today_preview.html").write_text(_today_html(dataset), encoding="utf-8")
    wx_parts = [f"# {chunk['title']}\n\n{chunk['content']}" for chunk in chunks]
    (output_dir / "wxpusher_preview.html").write_text("\n<hr>\n".join(wx_parts), encoding="utf-8")
    total = max(1, chinese["total_items"])
    ready = bool(
        parity["family_id_parity"] and parity["order_parity"]
        and chinese["chinese_names"] / total >= 0.90
        and chinese["chinese_descriptions"] / total >= 0.90
    )
    blockers = [] if ready else ["Chinese-first coverage is incomplete; English fallbacks remain."]
    (output_dir / "cutover_readiness.md").write_text(
        f"# Phase 11F.1 Cutover Readiness\n\nREADY_FOR_UI_CUTOVER: **{str(ready).upper()}**\n\n" +
        ("Blocking issues: none.\n" if not blockers else "Blocking issues:\n" + "\n".join(f"- {value}" for value in blockers)),
        encoding="utf-8",
    )
    return {"audit": audit, "dataset": dataset, "chunks": chunks, "parity": parity, "chinese": chinese, "ready": ready, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".phase11f-preview")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--enrich-chinese", action="store_true")
    parser.add_argument("--artifacts-only", action="store_true")
    parser.add_argument("--record-ai-failures", type=int, default=0)
    parser.add_argument("--deterministic-fallback", action="store_true")
    args = parser.parse_args()
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")
    if args.audit_only:
        report = audit_production()
        args.output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(args.output_dir / "production_audit.json", report)
        print(json.dumps(report, ensure_ascii=False, default=str))
        return 0
    if args.artifacts_only:
        import db
        from postgres_backend import initialize_evidence_schema
        report = audit_production()
        dataset = db.get_persisted_daily_discovery(pipeline_run_id=report["pipeline_run_id"])
        if not dataset:
            raise SystemExit("Persisted Daily Discovery preview is missing")
        enrichment = {
            "generated_names": 0, "generated_descriptions": 0,
            "ai_failures": args.record_ai_failures, "api_calls": 0,
        }
        if args.deterministic_fallback:
            from chinese_enrichment import apply_deterministic_fallback
            initialize_evidence_schema(db.DATABASE_SETTINGS.database_url)
            enrichment.update(apply_deterministic_fallback(dataset))
            dataset = db.get_persisted_daily_discovery(pipeline_run_id=report["pipeline_run_id"])
        result = write_preview_artifacts(args.output_dir, report, dataset, enrichment)
    else:
        result = build_preview(args.output_dir, enrich=args.enrich_chinese)
    print(json.dumps({
        "audit": result["audit"], "count": result["dataset"]["item_count"],
        "chunks": len(result["chunks"]), "parity": result["parity"],
        "chinese": result["chinese"], "ready": result["ready"], "blockers": result["blockers"],
        "first_family": result["dataset"]["items"][0]["canonical_name"] if result["dataset"]["items"] else None,
        "last_family": result["dataset"]["items"][-1]["canonical_name"] if result["dataset"]["items"] else None,
    }, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
