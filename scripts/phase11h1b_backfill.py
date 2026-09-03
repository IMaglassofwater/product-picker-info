"""Plan the narrowly scoped Phase 11H.1B Reddit identity backfill.

This command is dry-run only. It never writes production or local records.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db
from daily_picks import prepare_discovery_item


def plan(dataset: dict) -> list[dict]:
    changes = []
    for item in dataset.get("items", []):
        if not any("reddit" in str(source).casefold() for source in item.get("source_platforms", [])):
            continue
        corrected = prepare_discovery_item(item)
        before = item.get("canonical_name")
        after = corrected.get("canonical_name") if corrected.get("identity_valid") else None
        if before != after or item.get("canonical_name_zh") != corrected.get("canonical_name_zh"):
            changes.append({
                "family_id": item.get("family_id"), "before": before, "after": after,
                "chinese_after": corrected.get("canonical_name_zh"),
                "confidence": corrected.get("identity_confidence"),
                "method": corrected.get("identity_method"),
            })
    return changes


def main() -> int:
    dataset = db.get_persisted_daily_discovery()
    if not dataset:
        raise SystemExit("Persisted Daily Discovery is missing")
    report = {"dry_run": True, "changes": plan(dataset)}
    output = ROOT / ".phase11h-preview" / "phase11h1b_backfill_plan.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"dry_run": True, "changes": len(report["changes"]), "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
