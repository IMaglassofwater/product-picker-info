"""Manual GitHub Actions entry point for Phase 11D production operations."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase11d_reset import (  # noqa: E402
    Phase11DSafetyError, audit_production, require_database_url,
    reset_non_favorites, validate_fresh_run,
)


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser()
    subcommands = command.add_subparsers(dest="mode", required=True)
    audit = subcommands.add_parser("audit")
    audit.add_argument("--output-dir", type=Path, required=True)
    reset = subcommands.add_parser("reset")
    reset.add_argument("--output-dir", type=Path, required=True)
    reset.add_argument("--confirm", required=True)
    reset.add_argument("--apply-additive-schema", action="store_true")
    validate = subcommands.add_parser("validate")
    validate.add_argument("--output-dir", type=Path, required=True)
    validate.add_argument("--reset-result", type=Path, required=True)
    return command


def main() -> int:
    arguments = parser().parse_args()
    try:
        database_url = require_database_url()
        if arguments.mode == "audit":
            result = audit_production(database_url, arguments.output_dir)
            print("Phase 11D production audit complete")
            print(f"Schema compatible: {result['schema']['compatible']}")
            print(f"Products: {result['summary']['products']}")
            print(f"Favorited Products: {result['summary']['favorited_products']}")
            print(f"Safe to prepare reset: {result['summary']['safe_to_prepare_reset']}")
        elif arguments.mode == "reset":
            result = reset_non_favorites(
                database_url, arguments.confirm, arguments.output_dir,
                apply_additive_schema=arguments.apply_additive_schema,
            )
            print("Phase 11D reset complete")
            print(f"Backup schema: {result['backup']['schema']}")
            print(f"Backup rows: {result['backup']['row_count']}")
            print(f"Products deleted: {result['products_deleted']}")
            print(f"Favorited Products preserved: {result['favorites_after']['favorited_products']}")
        else:
            result = validate_fresh_run(
                database_url, arguments.output_dir, arguments.reset_result,
            )
            print("Phase 11D fresh validation complete")
            print(f"Run ID: {result['run_id']}")
            print(f"Observed: {result['totals']['observed']}")
            print(f"Daily Discovery Families: {result['totals']['daily_discovery_families']}")
            print(f"Likely False Negatives: {len(result['likely_false_negatives'])}")
            print(f"Suspicious Passes: {len(result['suspicious_passes'])}")
        return 0
    except Phase11DSafetyError as exc:
        print(f"Phase 11D safety stop: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
