"""Safe cloud database reachability and minimal data-path smoke test."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import db
from database_backend import get_database_settings


def run_smoke(*, read_only: bool = False) -> dict[str, object]:
    settings = get_database_settings()
    if settings.backend == "sqlite" and not db.init_db():
        raise RuntimeError("database initialization failed")
    with db._connect() as connection:
        products = connection.execute("SELECT COUNT(*) AS count FROM products").fetchone()["count"]
        runs = connection.execute("SELECT COUNT(*) AS count FROM pipeline_runs").fetchone()["count"]
        feedback_writable: bool | str = "not tested"
        if not read_only:
            marker = f"cloud-smoke-{uuid4().hex}"
            now = db._utc_now()
            connection.execute(
                """INSERT INTO user_product_feedback
                   (entity_type, entity_id, feedback_type, note, created_at, updated_at)
                   VALUES (?, ?, 'WATCH', 'cloud smoke test', ?, ?)""",
                ("smoke_test", marker, now, now),
            )
            connection.execute(
                "DELETE FROM user_product_feedback WHERE entity_type=? AND entity_id=?",
                ("smoke_test", marker),
            )
            feedback_writable = True
    return {
        "backend": settings.backend,
        "products": products,
        "pipeline_runs": runs,
        "feedback_writable": feedback_writable,
        "read_only": read_only,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--read-only", action="store_true")
    args = parser.parse_args(argv)
    result = run_smoke(read_only=args.read_only)
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
