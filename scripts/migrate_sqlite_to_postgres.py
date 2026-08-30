"""Inventory a complete SQLite-to-PostgreSQL migration; dry-run by default."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import sqlite3
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database_backend import DEFAULT_SQLITE_PATH, require_postgres_url


@dataclass(frozen=True)
class MigrationDryRun:
    source: Path
    table_counts: dict[str, int]
    total_rows: int


@dataclass(frozen=True)
class ProductionSelection:
    keep: int
    skip: int


REAL_SOURCES = {
    "reddit", "reddit_arctic_shift", "amazon", "kickstarter",
    "indiegogo", "product_hunt", "yanko_design",
}


def inspect_sqlite(source: Path = DEFAULT_SQLITE_PATH) -> MigrationDryRun:
    """Read every application table and return exact counts without writes."""
    if not source.is_file():
        raise FileNotFoundError(source)
    uri = f"file:{source.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        tables = [
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in tables
        }
    return MigrationDryRun(source.resolve(), counts, sum(counts.values()))


def inspect_production_selection(source: Path = DEFAULT_SQLITE_PATH) -> dict[str, ProductionSelection]:
    """Classify current rows for a future production-only copy without writes."""
    uri = f"file:{source.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        placeholders = ",".join("?" for _ in REAL_SOURCES)

        def split(table: str, where: str, params=()) -> ProductionSelection:
            total = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            keep = connection.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE {where}', params
            ).fetchone()[0]
            return ProductionSelection(keep, total - keep)

        products = split(
            "products", f"lower(source_platform) IN ({placeholders})", tuple(REAL_SOURCES)
        )
        snapshots = split(
            "product_metric_snapshots",
            f"lower(source_platform) IN ({placeholders})",
            tuple(REAL_SOURCES),
        )
        gemini = split("ai_triage_results", "lower(provider)='gemini'")
        mock = split("ai_triage_results", "lower(provider)='mock'")
        # Current v1/v2 analysis rows were generated during validation phases.
        deep = split("deep_analysis_results", "analysis_version LIKE 'production_%'")
        software = split("software_analysis_results", "analysis_version LIKE 'production_%'")
        specificity = split("specificity_results", "1=1")
        # Existing local feedback is development/UI-test state until explicitly reviewed.
        feedback = split("user_product_feedback", "0=1")
        pipeline = split(
            "pipeline_runs",
            "EXISTS (SELECT 1 FROM pipeline_source_runs s "
            "WHERE s.run_id=pipeline_runs.run_id AND s.fetched > 0)",
        )
    return {
        "Products": products,
        "Metric Snapshots": snapshots,
        "Gemini Triage": ProductionSelection(gemini.keep, 0),
        "Mock Triage": ProductionSelection(0, mock.keep),
        "Deep Analysis": deep,
        "Software Analysis": software,
        "Specificity": specificity,
        "Feedback": feedback,
        "Pipeline Runs": pipeline,
    }


def _production_rows(connection: sqlite3.Connection) -> dict[str, list[sqlite3.Row]]:
    """Return dependency-ordered production rows for an explicitly approved copy."""
    connection.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in REAL_SOURCES)
    sources = tuple(REAL_SOURCES)
    queries = {
        "products": (f"SELECT * FROM products WHERE lower(source_platform) IN ({placeholders})", sources),
        "processed_projects": (
            f"SELECT x.* FROM processed_projects x JOIN products p ON p.url=x.url "
            f"WHERE lower(p.source_platform) IN ({placeholders})", sources,
        ),
        "micro_innovation_candidates": (
            f"SELECT c.* FROM micro_innovation_candidates c JOIN products p ON p.url=c.source_url "
            f"WHERE lower(p.source_platform) IN ({placeholders})", sources,
        ),
        "ai_triage_results": ("SELECT * FROM ai_triage_results WHERE lower(provider)='gemini'", ()),
        "deep_analysis_results": ("SELECT * FROM deep_analysis_results WHERE analysis_version LIKE 'production_%'", ()),
        "software_analysis_results": ("SELECT * FROM software_analysis_results WHERE analysis_version LIKE 'production_%'", ()),
        "product_metric_snapshots": (
            f"SELECT m.* FROM product_metric_snapshots m JOIN products p ON p.id=m.product_id "
            f"WHERE lower(p.source_platform) IN ({placeholders})", sources,
        ),
        "pipeline_runs": (
            "SELECT r.* FROM pipeline_runs r WHERE EXISTS (SELECT 1 FROM pipeline_source_runs s WHERE s.run_id=r.run_id AND s.fetched>0)", (),
        ),
        "pipeline_source_runs": (
            "SELECT s.* FROM pipeline_source_runs s JOIN pipeline_runs r ON r.run_id=s.run_id "
            "WHERE EXISTS (SELECT 1 FROM pipeline_source_runs x WHERE x.run_id=r.run_id AND x.fetched>0)", (),
        ),
        "specificity_results": ("SELECT * FROM specificity_results", ()),
        "user_product_feedback": ("SELECT * FROM user_product_feedback WHERE 0=1", ()),
        "re_evaluation_requests": ("SELECT * FROM re_evaluation_requests WHERE 0=1", ()),
        "product_eligibility": (
            f"SELECT e.* FROM product_eligibility e JOIN products p ON p.id=e.product_id "
            f"WHERE lower(p.source_platform) IN ({placeholders})", sources,
        ),
        "product_identities": (
            f"SELECT i.* FROM product_identities i JOIN products p ON p.id=i.product_id "
            f"WHERE lower(p.source_platform) IN ({placeholders})", sources,
        ),
        "product_families": (
            f"SELECT DISTINCT f.* FROM product_families f "
            f"JOIN product_family_members fm ON fm.family_id=f.id "
            f"JOIN products p ON p.id=fm.product_id "
            f"WHERE lower(p.source_platform) IN ({placeholders})", sources,
        ),
        "product_family_members": (
            f"SELECT fm.* FROM product_family_members fm JOIN products p ON p.id=fm.product_id "
            f"WHERE lower(p.source_platform) IN ({placeholders})", sources,
        ),
        "product_observations": (
            f"SELECT o.* FROM product_observations o JOIN products p ON p.id=o.product_id "
            f"WHERE lower(p.source_platform) IN ({placeholders}) "
            "AND EXISTS (SELECT 1 FROM pipeline_runs r WHERE r.run_id=o.pipeline_run_id)", sources,
        ),
        "source_evidence_snapshots": (
            f"SELECT e.* FROM source_evidence_snapshots e JOIN products p ON p.id=e.product_id "
            f"WHERE lower(p.source_platform) IN ({placeholders})", sources,
        ),
    }
    return {table: connection.execute(sql, params).fetchall() for table, (sql, params) in queries.items()}


def execute_production_migration(source: Path, database_url: str) -> dict[str, int]:
    """Copy the reviewed production set. Caller must explicitly pass --execute."""
    from postgres_backend import initialize_postgres_schema, postgres_connection

    initialize_postgres_schema(database_url)
    uri = f"file:{source.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as sqlite_connection:
        selected = _production_rows(sqlite_connection)
    boolean_columns = {
        "ai_triage_results": {"needs_deep_analysis"},
        "pipeline_source_runs": {"failed"},
        "product_family_members": {"reviewed", "manual_override"},
        "product_observations": {"was_new", "was_updated"},
    }
    copied: dict[str, int] = {}
    with postgres_connection(database_url) as target:
        for table, rows in selected.items():
            copied[table] = len(rows)
            for row in rows:
                columns = tuple(row.keys())
                values = [bool(row[name]) if name in boolean_columns.get(table, set()) else row[name] for name in columns]
                names = ", ".join(f'"{name}"' for name in columns)
                markers = ", ".join("?" for _ in columns)
                target.execute(
                    f'INSERT INTO "{table}" ({names}) VALUES ({markers}) ON CONFLICT DO NOTHING',
                    tuple(values),
                )
        identity_tables = {
            "products", "processed_projects", "micro_innovation_candidates",
            "ai_triage_results", "deep_analysis_results", "software_analysis_results",
            "product_metric_snapshots", "pipeline_source_runs", "specificity_results",
            "user_product_feedback", "re_evaluation_requests",
            "product_families", "product_family_members", "product_observations",
            "source_evidence_snapshots",
        }
        for table in identity_tables:
            if copied.get(table):
                target.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f'COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM "{table}"'
                )
        for table, expected in copied.items():
            actual = target.execute(f'SELECT COUNT(*) AS count FROM "{table}"').fetchone()["count"]
            if actual != expected:
                raise RuntimeError(f"migration verification failed for {table}")
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SQLITE_PATH)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Explicitly request the default read-only mode")
    parser.add_argument("--production-only", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    report = inspect_sqlite(args.source)
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")
    print(f"Source: {report.source}")
    if args.production_only:
        print("Selection: PRODUCTION ONLY")
        for label, selection in inspect_production_selection(args.source).items():
            print(f"{label}: KEEP {selection.keep} / SKIP {selection.skip}")
    else:
        for table, count in report.table_counts.items():
            print(f"{table}: {count}")
        print(f"Total rows: {report.total_rows}")
    if args.execute:
        if not args.production_only:
            parser.error("--execute requires --production-only")
        database_url = require_postgres_url()
        copied = execute_production_migration(args.source, database_url)
        print("Migration verified:")
        for table, count in copied.items():
            print(f"{table}: {count}")
        print("Validation: production migration completed and verified")
    else:
        print("Validation: complete table inventory readable; no writes performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
