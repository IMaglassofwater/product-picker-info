"""Phase 11 evidence-first shadow orchestration and safe debug reporting."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from types import SimpleNamespace
import sys
import time
from typing import Iterable

import db
from evidence_foundation import (
    assess_evidence_strength,
    classify_concrete_product,
    classify_eligibility,
    extract_evidence,
    family_match,
    normalize_identity,
)
from models import Product


def _from_record(record: dict):
    raw = record.get("raw_data") or {}
    if isinstance(raw, str):
        raw = json.loads(raw or "{}")
    # Historical rows may predate today's strict Product constructor (for
    # example, a source may legitimately have no image). Shadow projection
    # reads those facts without mutating or fabricating missing source fields.
    return SimpleNamespace(
        project_id=record.get("project_id") or "", source_platform=record.get("source_platform") or "",
        url=record.get("url") or "", title=record.get("title") or "",
        description=record.get("description") or "", category=record.get("category") or "",
        image_url=record.get("image_url") or "", raw_data=raw,
    )


def project_product(
    product_id: int,
    product: Product,
    *,
    run_id: str | None = None,
    was_new: bool = False,
    was_updated: bool = False,
) -> dict:
    """Build and persist one shadow projection from already available facts."""
    eligibility = classify_eligibility(product)
    concrete = classify_concrete_product(product, eligibility)
    identity = normalize_identity(product, eligibility, concrete=concrete)
    family = family_match(identity, eligibility.content_type, product.category)
    facts = extract_evidence(product)
    saved = db.save_shadow_product_foundation(
        product_id, product, eligibility, concrete, identity, family, facts,
        pipeline_run_id=run_id, was_new=was_new, was_updated=was_updated,
    )
    return {
        **saved, "eligibility": eligibility, "concrete": concrete, "identity": identity,
        "family": family, "facts": facts,
        "strength": assess_evidence_strength(product.source_platform, facts),
    }


def process_products_for_run(
    run_id: str,
    products: Iterable[Product],
    *,
    existing_urls: set[str] | None = None,
    deadline_monotonic: float | None = None,
    monotonic=time.monotonic,
) -> dict:
    """Record run membership after the legacy source batch saved successfully."""
    existing = existing_urls or set()
    items = list(products)
    results = []
    deferred = 0
    failed = 0
    for index, product in enumerate(items):
        if deadline_monotonic is not None and monotonic() >= deadline_monotonic:
            deferred += len(items) - index
            break
        record = db.get_product_record_by_url(product.url)
        if not record:
            failed += 1
            deferred += len(items) - index - 1
            break
        projected = project_product(
            record["id"], product, run_id=run_id,
            was_new=product.url not in existing,
            was_updated=product.url in existing,
        )
        if not projected["observed"]:
            failed += 1
            deferred += len(items) - index - 1
            break
        results.append(projected)
    if deadline_monotonic is None or monotonic() < deadline_monotonic:
        db.refresh_shadow_family_canonical_names()
    if deadline_monotonic is None or monotonic() < deadline_monotonic:
        db.prune_empty_shadow_families()
    return {
        "processed": len(results),
        "failed": failed,
        "deferred": deferred,
        "observed": sum(bool(item["observed"]) for item in results),
        "eligible": sum(item["eligibility"].eligibility_status == "ELIGIBLE" for item in results),
        "ineligible": sum(item["eligibility"].eligibility_status == "INELIGIBLE" for item in results),
        "ambiguous": sum(item["eligibility"].eligibility_status == "AMBIGUOUS" for item in results),
        "concrete": sum(item["concrete"].status == "CONCRETE" for item in results),
        "non_concrete": sum(item["concrete"].status == "NON_CONCRETE" for item in results),
        "concrete_ambiguous": sum(item["concrete"].status == "AMBIGUOUS" for item in results),
    }


def backfill_historical(*, limit: int | None = None) -> dict:
    """Deterministically backfill identities/families/evidence, never observations."""
    records = db.get_all_product_records()
    if limit is not None:
        records = records[: max(0, limit)]
    results = []
    for record in records:
        try:
            results.append(project_product(record["id"], _from_record(record)))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    canonical_names_refreshed = db.refresh_shadow_family_canonical_names()
    orphan_families_removed = db.prune_empty_shadow_families()
    return {
        "processed": len(results),
        "eligible": sum(item["eligibility"].eligibility_status == "ELIGIBLE" for item in results),
        "ineligible": sum(item["eligibility"].eligibility_status == "INELIGIBLE" for item in results),
        "ambiguous": sum(item["eligibility"].eligibility_status == "AMBIGUOUS" for item in results),
        "normalized_high": sum(item["identity"].confidence == "HIGH" for item in results),
        "normalized_medium": sum(item["identity"].confidence == "MEDIUM" for item in results),
        "unresolved": sum(item["identity"].confidence == "UNRESOLVED" for item in results),
        "evidence_records": sum(len(item["facts"]) for item in results),
        "orphan_families_removed": orphan_families_removed,
        "canonical_names_refreshed": canonical_names_refreshed,
    }


def backfill_latest_supported_run() -> dict:
    """Backfill latest run observations only when timestamps/source ledger prove them."""
    run = db.get_latest_completed_run()
    if not run:
        return {"run_id": None, "supported_records": 0, "observed": 0}
    records = db.get_supported_product_records_for_run(run["run_id"])
    results = []
    for record in records:
        try:
            results.append(project_product(
                record["id"], _from_record(record), run_id=run["run_id"],
                was_new=False, was_updated=True,
            ))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return {
        "run_id": run["run_id"], "supported_records": len(records),
        "observed": sum(bool(item["observed"]) for item in results),
    }


def build_shadow_report(run_id: str | None = None) -> dict:
    """Return inspectable shadow counts without ranking or limiting families."""
    counts = db.get_shadow_counts()
    discovery = db.get_daily_discovery(run_id)
    types = Counter(item["product_type"] for item in discovery)
    strengths = Counter(item.get("evidence_strength", "WEAK") for item in discovery)
    return {
        "database": counts,
        "latest_run": (run_id or (db.get_latest_completed_run() or {}).get("run_id")),
        "daily_discovery_count": len(discovery),
        "product_types": dict(types),
        "evidence_strength": dict(strengths),
        "family_names": [item["canonical_name"] for item in discovery],
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Evidence-first shadow debug tool")
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--run-id")
    parser.add_argument("--latest-supported-run", action="store_true")
    args = parser.parse_args(argv)
    if not db.init_db():
        print("Shadow database initialization failed")
        return 1
    if args.backfill:
        print(json.dumps(backfill_historical(limit=args.limit), ensure_ascii=False, indent=2))
    if args.latest_supported_run:
        print(json.dumps(backfill_latest_supported_run(), ensure_ascii=False, indent=2))
    print(json.dumps(build_shadow_report(args.run_id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
