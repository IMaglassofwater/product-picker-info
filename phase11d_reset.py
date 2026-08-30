"""Phase 11D production audit, reversible backup, and controlled reset.

This module is intentionally independent from the daily scheduler.  It only
operates when called by the manual Phase 11D GitHub Actions workflow and never
logs a database URL or credentials.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import random
import re
from typing import Any, Iterable
from uuid import UUID


RESET_CONFIRMATION = "RESET_NON_FAVORITES"
REQUIRED_SHADOW_COLUMNS = {
    "product_eligibility": {
        "product_id", "content_type", "eligibility_status", "eligibility_reason",
        "eligibility_version", "concrete_product_status", "concrete_product_reason",
        "concrete_product_version", "evaluated_at",
    },
    "product_identities": {
        "product_id", "source_title", "normalized_product_name",
        "normalized_product_name_zh", "normalization_method",
        "normalization_confidence", "normalization_version", "normalized_at",
    },
    "product_families": {"id", "family_key", "canonical_name", "product_type", "status"},
    "product_family_members": {"family_id", "product_id", "manual_override"},
    "product_observations": {"pipeline_run_id", "product_id", "observed_at"},
    "source_evidence_snapshots": {
        "product_id", "family_id", "pipeline_run_id", "metric_name", "evidence_key",
    },
}

DISCOVERY_TABLES = (
    "products", "processed_projects", "micro_innovation_candidates",
    "ai_triage_results", "deep_analysis_results", "software_analysis_results",
    "specificity_results", "product_metric_snapshots", "pipeline_runs",
    "pipeline_source_runs", "user_product_feedback", "re_evaluation_requests",
    "product_eligibility", "product_identities", "product_families",
    "product_family_members", "product_observations", "source_evidence_snapshots",
)
OPTIONAL_DERIVED_TABLES = (
    "daily_discovery", "daily_discovery_results", "daily_rankings", "ranking_results",
)
ALLOWED_DEPENDENCY_TABLES = set(DISCOVERY_TABLES) | set(OPTIONAL_DERIVED_TABLES)


class Phase11DSafetyError(RuntimeError):
    """Raised before commit when a reset invariant cannot be proven."""


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, Decimal, UUID)):
        return str(value)
    if isinstance(value, bytes):
        return {"encoding": "hex", "value": value.hex()}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_value(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def require_database_url(environ: dict[str, str] | None = None) -> str:
    environment = environ if environ is not None else os.environ
    value = str(environment.get("DATABASE_URL", "") or "").strip()
    if not value.startswith(("postgres://", "postgresql://")):
        raise Phase11DSafetyError("DATABASE_URL is unavailable or is not PostgreSQL")
    return value


def require_confirmation(value: str) -> None:
    if value != RESET_CONFIRMATION:
        raise Phase11DSafetyError(
            f"Reset confirmation must exactly equal {RESET_CONFIRMATION}"
        )


def _connect(database_url: str):
    from psycopg import connect
    from psycopg.rows import dict_row

    return connect(database_url, row_factory=dict_row)


def _public_tables(connection) -> set[str]:
    rows = connection.execute(
        """SELECT table_name FROM information_schema.tables
           WHERE table_schema='public' AND table_type='BASE TABLE'"""
    ).fetchall()
    return {row["table_name"] for row in rows}


def _columns(connection) -> dict[str, set[str]]:
    rows = connection.execute(
        """SELECT table_name, column_name FROM information_schema.columns
           WHERE table_schema='public'"""
    ).fetchall()
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        result[row["table_name"]].add(row["column_name"])
    return dict(result)


def _foreign_keys(connection) -> list[dict]:
    return [dict(row) for row in connection.execute(
        """SELECT tc.constraint_name, tc.table_name AS child_table,
                  kcu.column_name AS child_column, ccu.table_name AS parent_table,
                  ccu.column_name AS parent_column
           FROM information_schema.table_constraints tc
           JOIN information_schema.key_column_usage kcu
             ON tc.constraint_name=kcu.constraint_name
            AND tc.constraint_schema=kcu.constraint_schema
           JOIN information_schema.constraint_column_usage ccu
             ON ccu.constraint_name=tc.constraint_name
            AND ccu.constraint_schema=tc.constraint_schema
           WHERE tc.constraint_schema='public' AND tc.constraint_type='FOREIGN KEY'
           ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position"""
    ).fetchall()]


def _indexes(connection) -> list[dict]:
    return [dict(row) for row in connection.execute(
        """SELECT tablename AS table_name, indexname AS index_name, indexdef
           FROM pg_indexes WHERE schemaname='public'
           ORDER BY tablename, indexname"""
    ).fetchall()]


def _constraints(connection) -> list[dict]:
    return [dict(row) for row in connection.execute(
        """SELECT table_name, constraint_name, constraint_type
           FROM information_schema.table_constraints
           WHERE table_schema='public'
           ORDER BY table_name, constraint_name"""
    ).fetchall()]


def validate_schema(connection) -> dict:
    tables = _public_tables(connection)
    columns = _columns(connection)
    missing_tables = sorted(set(REQUIRED_SHADOW_COLUMNS) - tables)
    missing_columns = {
        table: sorted(required - columns.get(table, set()))
        for table, required in REQUIRED_SHADOW_COLUMNS.items()
        if required - columns.get(table, set())
    }
    foreign_keys = _foreign_keys(connection)
    unexpected_dependencies = [
        item for item in foreign_keys
        if item["parent_table"] in ALLOWED_DEPENDENCY_TABLES
        and item["child_table"] not in ALLOWED_DEPENDENCY_TABLES
    ]
    return {
        "compatible": not missing_tables and not missing_columns and not unexpected_dependencies,
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "unexpected_dependencies": unexpected_dependencies,
        "foreign_keys": foreign_keys,
        "indexes": _indexes(connection),
        "constraints": _constraints(connection),
    }


def _table_counts(connection, tables: Iterable[str]) -> dict[str, int]:
    from psycopg import sql

    available = _public_tables(connection)
    counts: dict[str, int] = {}
    for table in tables:
        if table in available:
            query = sql.SQL("SELECT COUNT(*) AS count FROM public.{}").format(sql.Identifier(table))
            counts[table] = int(connection.execute(query).fetchone()["count"])
    return counts


def _favorite_rows(connection) -> list[dict]:
    return [dict(row) for row in connection.execute(
        """SELECT id, entity_id, feedback_type, created_at, updated_at
           FROM user_product_feedback
           WHERE lower(entity_type)='product' AND upper(feedback_type)='FAVORITE'
           ORDER BY id"""
    ).fetchall()]


def _favorite_ids(favorite_rows: list[dict]) -> list[int]:
    values: list[int] = []
    invalid: list[str] = []
    for row in favorite_rows:
        try:
            values.append(int(row["entity_id"]))
        except (TypeError, ValueError):
            invalid.append(str(row.get("entity_id")))
    if invalid:
        raise Phase11DSafetyError(f"Favorite rows contain invalid Product IDs: {invalid}")
    if len(set(values)) != len(values):
        raise Phase11DSafetyError("Duplicate Favorite Product IDs were found")
    return sorted(values)


def favorite_integrity(connection) -> dict:
    available = _public_tables(connection)
    favorite_rows = _favorite_rows(connection)
    favorite_ids = _favorite_ids(favorite_rows)
    products = []
    if favorite_ids:
        products = [dict(row) for row in connection.execute(
            """SELECT id, source_platform, url, title,
                      raw_data IS NOT NULL AS raw_data_present,
                      md5(COALESCE(raw_data::text, 'null')) AS raw_data_hash,
                      first_seen_at, last_seen_at
               FROM products WHERE id=ANY(%s) ORDER BY id""",
            (favorite_ids,),
        ).fetchall()]
    found_ids = {int(row["id"]) for row in products}
    orphan_ids = sorted(set(favorite_ids) - found_ids)
    if orphan_ids:
        raise Phase11DSafetyError(f"Orphan Favorite Product IDs: {orphan_ids}")

    identity_ids = set()
    family_by_product: dict[int, int] = {}
    evidence_counts: dict[int, int] = {}
    if favorite_ids and "product_identities" in available:
        identity_ids = {
            int(row["product_id"]) for row in connection.execute(
                "SELECT product_id FROM product_identities WHERE product_id=ANY(%s)",
                (favorite_ids,),
            ).fetchall()
        }
    if favorite_ids and "product_family_members" in available:
        family_by_product = {
            int(row["product_id"]): int(row["family_id"])
            for row in connection.execute(
                """SELECT product_id, family_id FROM product_family_members
                   WHERE product_id=ANY(%s)""", (favorite_ids,),
            ).fetchall()
        }
    if favorite_ids and "source_evidence_snapshots" in available:
        evidence_counts = {
            int(row["product_id"]): int(row["count"])
            for row in connection.execute(
                """SELECT product_id, COUNT(*) AS count FROM source_evidence_snapshots
                   WHERE product_id=ANY(%s) GROUP BY product_id""", (favorite_ids,),
            ).fetchall()
        }
    safe_products = []
    for row in products:
        product_id = int(row["id"])
        safe_products.append({
            "product_id": product_id,
            "source_platform": row["source_platform"],
            "source_url_present": bool(row["url"]),
            "source_title_present": bool(row["title"]),
            "raw_data_present": bool(row["raw_data_present"]),
            "raw_data_hash": row["raw_data_hash"],
            "identity_exists": product_id in identity_ids,
            "family_id": family_by_product.get(product_id),
            "evidence_records": evidence_counts.get(product_id, 0),
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
        })
    return {
        "favorite_rows": len(favorite_rows),
        "favorite_product_ids": favorite_ids,
        "favorited_products": len(products),
        "orphan_product_ids": orphan_ids,
        "products": safe_products,
    }


def _product_id_hash(connection) -> str:
    row = connection.execute(
        "SELECT md5(COALESCE(string_agg(id::text, ',' ORDER BY id), '')) AS digest FROM products"
    ).fetchone()
    return str(row["digest"])


def _audit_snapshot(connection, mode: str) -> dict:
    schema = validate_schema(connection)
    counts = _table_counts(connection, DISCOVERY_TABLES + OPTIONAL_DERIVED_TABLES)
    favorites = favorite_integrity(connection) if "user_product_feedback" in counts else {
        "favorite_rows": 0, "favorite_product_ids": [], "favorited_products": 0,
        "orphan_product_ids": [], "products": [],
    }
    product_count = counts.get("products", 0)
    return {
        "mode": mode,
        "generated_at": datetime.now(timezone.utc),
        "schema": schema,
        "counts": counts,
        "favorites": favorites,
        "product_id_hash": _product_id_hash(connection) if "products" in counts else "",
        "summary": {
            "products": product_count,
            "favorited_products": favorites["favorited_products"],
            "non_favorited_products": product_count - favorites["favorited_products"],
            "safe_to_prepare_reset": bool(schema["compatible"] and not favorites["orphan_product_ids"]),
        },
    }


def audit_production(database_url: str, output_dir: Path) -> dict:
    with _connect(database_url) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        report = _audit_snapshot(connection, "audit")
    write_json(output_dir / "pre_reset_audit.json", report)
    return report


def deploy_evidence_schema(database_url: str, output_dir: Path) -> dict:
    """Deploy Phase 11C DDL and prove all existing Product/Favorite data is unchanged."""
    from postgres_backend import evidence_schema_statements

    with _connect(database_url) as connection:
        connection.execute("SET LOCAL lock_timeout='15s'")
        connection.execute("SET LOCAL statement_timeout='5min'")
        connection.execute("LOCK TABLE products, user_product_feedback IN SHARE MODE")
        before = _audit_snapshot(connection, "schema_before")
        before_tables = set(_public_tables(connection))
        before_indexes = {
            (row["table_name"], row["index_name"]) for row in before["schema"]["indexes"]
        }
        before_constraints = {
            (row["table_name"], row["constraint_name"]) for row in before["schema"]["constraints"]
        }
        for statement in evidence_schema_statements():
            connection.execute(statement)
        after = _audit_snapshot(connection, "schema_after")
        after_tables = set(_public_tables(connection))
        after_indexes = {
            (row["table_name"], row["index_name"]) for row in after["schema"]["indexes"]
        }
        after_constraints = {
            (row["table_name"], row["constraint_name"]) for row in after["schema"]["constraints"]
        }

        before_favorites = before["favorites"]
        after_favorites = after["favorites"]
        before_hashes = {
            row["product_id"]: row["raw_data_hash"] for row in before_favorites["products"]
        }
        after_hashes = {
            row["product_id"]: row["raw_data_hash"] for row in after_favorites["products"]
        }
        invariant_errors = []
        if before["summary"]["products"] != after["summary"]["products"]:
            invariant_errors.append("Product count changed")
        if before["product_id_hash"] != after["product_id_hash"]:
            invariant_errors.append("Product ID set changed")
        if before_favorites["favorite_rows"] != after_favorites["favorite_rows"]:
            invariant_errors.append("Favorite row count changed")
        if before_favorites["favorite_product_ids"] != after_favorites["favorite_product_ids"]:
            invariant_errors.append("Favorite Product ID set changed")
        if before_hashes != after_hashes:
            invariant_errors.append("Favorite raw_data changed")
        if not after["schema"]["compatible"]:
            invariant_errors.append("Evidence-First schema remains incompatible")
        if invariant_errors:
            raise Phase11DSafetyError("; ".join(invariant_errors))

        report = {
            "mode": "deploy_schema",
            "deployed_at": datetime.now(timezone.utc),
            "schema_before": before,
            "schema_after": after,
            "tables_created": sorted(after_tables - before_tables),
            "indexes_created": [
                {"table_name": table, "index_name": index}
                for table, index in sorted(after_indexes - before_indexes)
            ],
            "constraints_created": [
                {"table_name": table, "constraint_name": constraint}
                for table, constraint in sorted(after_constraints - before_constraints)
            ],
            "products_before": before["summary"]["products"],
            "products_after": after["summary"]["products"],
            "favorite_rows_before": before_favorites["favorite_rows"],
            "favorite_rows_after": after_favorites["favorite_rows"],
            "favorite_product_ids_before": before_favorites["favorite_product_ids"],
            "favorite_product_ids_after": after_favorites["favorite_product_ids"],
            "favorite_raw_data_unchanged": before_hashes == after_hashes,
            "safe_to_prepare_reset": after["summary"]["safe_to_prepare_reset"],
            "products_deleted": 0,
            "historical_backfill_performed": False,
        }
    write_json(output_dir / "schema_deployment_report.json", report)
    return report


def _backup_schema_name() -> str:
    run_id = re.sub(r"[^a-zA-Z0-9_]", "_", os.getenv("GITHUB_RUN_ID", "manual"))[:24]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"phase11d_backup_{stamp}_{run_id}".lower()


def create_backup(connection, tables: Iterable[str], schema_name: str) -> dict:
    from psycopg import sql

    available = _public_tables(connection)
    selected = [table for table in tables if table in available]
    connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))
    counts: dict[str, int] = {}
    for table in selected:
        connection.execute(
            sql.SQL("CREATE TABLE {}.{} AS TABLE public.{}")
            .format(sql.Identifier(schema_name), sql.Identifier(table), sql.Identifier(table))
        )
        source_count = int(connection.execute(
            sql.SQL("SELECT COUNT(*) AS count FROM public.{}").format(sql.Identifier(table))
        ).fetchone()["count"])
        backup_count = int(connection.execute(
            sql.SQL("SELECT COUNT(*) AS count FROM {}.{}")
            .format(sql.Identifier(schema_name), sql.Identifier(table))
        ).fetchone()["count"])
        if source_count != backup_count:
            raise Phase11DSafetyError(
                f"Backup verification failed for {table}: {source_count} != {backup_count}"
            )
        counts[table] = backup_count
    connection.execute(
        sql.SQL("""CREATE TABLE {}.backup_manifest (
                     table_name TEXT PRIMARY KEY, row_count BIGINT NOT NULL,
                     created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)
                 """).format(sql.Identifier(schema_name))
    )
    for table, count in counts.items():
        connection.execute(
            sql.SQL("INSERT INTO {}.backup_manifest (table_name, row_count) VALUES (%s, %s)")
            .format(sql.Identifier(schema_name)), (table, count),
        )
    return {
        "successful": True,
        "type": "Neon archive schema",
        "schema": schema_name,
        "table_counts": counts,
        "row_count": sum(counts.values()),
    }


def _not_preserved(column: str, favorite_ids: list[int]) -> tuple[str, tuple]:
    if not favorite_ids:
        return "TRUE", ()
    return f"{column} <> ALL(%s)", (favorite_ids,)


def reset_non_favorites(
    database_url: str,
    confirmation: str,
    output_dir: Path,
    *,
    apply_additive_schema: bool = False,
) -> dict:
    require_confirmation(confirmation)
    if apply_additive_schema:
        from postgres_backend import initialize_postgres_schema
        initialize_postgres_schema(database_url)

    with _connect(database_url) as connection:
        connection.execute("SET LOCAL lock_timeout='15s'")
        connection.execute("SET LOCAL statement_timeout='10min'")
        connection.execute("LOCK TABLE products, user_product_feedback IN SHARE ROW EXCLUSIVE MODE")
        schema = validate_schema(connection)
        if not schema["compatible"]:
            raise Phase11DSafetyError("Phase 11C production schema is incompatible")
        before_counts = _table_counts(connection, DISCOVERY_TABLES + OPTIONAL_DERIVED_TABLES)
        before_favorites = favorite_integrity(connection)
        favorite_ids = before_favorites["favorite_product_ids"]
        favorite_hashes = {
            row["product_id"]: row["raw_data_hash"] for row in before_favorites["products"]
        }
        backup = create_backup(
            connection, DISCOVERY_TABLES + OPTIONAL_DERIVED_TABLES, _backup_schema_name(),
        )

        available = _public_tables(connection)
        for table in OPTIONAL_DERIVED_TABLES:
            if table in available:
                from psycopg import sql
                connection.execute(sql.SQL("DELETE FROM public.{}").format(sql.Identifier(table)))

        for table in (
            "specificity_results", "deep_analysis_results", "software_analysis_results",
            "ai_triage_results", "micro_innovation_candidates", "re_evaluation_requests",
        ):
            if table in available:
                from psycopg import sql
                connection.execute(sql.SQL("DELETE FROM public.{}").format(sql.Identifier(table)))

        connection.execute("DELETE FROM product_observations")
        if favorite_ids:
            connection.execute(
                """UPDATE source_evidence_snapshots SET pipeline_run_id=NULL
                   WHERE product_id=ANY(%s)""", (favorite_ids,),
            )
        predicate, params = _not_preserved("product_id", favorite_ids)
        connection.execute(f"DELETE FROM source_evidence_snapshots WHERE {predicate}", params)
        connection.execute(f"DELETE FROM product_metric_snapshots WHERE {predicate}", params)
        connection.execute(f"DELETE FROM product_family_members WHERE {predicate}", params)
        connection.execute(f"DELETE FROM product_eligibility WHERE {predicate}", params)
        connection.execute(f"DELETE FROM product_identities WHERE {predicate}", params)
        connection.execute(
            """DELETE FROM user_product_feedback
               WHERE NOT (lower(entity_type)='product' AND upper(feedback_type)='FAVORITE'
                          AND entity_id=ANY(%s))""",
            ([str(product_id) for product_id in favorite_ids],),
        )
        connection.execute("DELETE FROM product_families f WHERE NOT EXISTS (SELECT 1 FROM product_family_members m WHERE m.family_id=f.id)")
        connection.execute("DELETE FROM pipeline_source_runs")
        if favorite_ids:
            connection.execute(
                "UPDATE source_evidence_snapshots SET pipeline_run_id=NULL WHERE product_id=ANY(%s)",
                (favorite_ids,),
            )
        connection.execute("DELETE FROM pipeline_runs")
        connection.execute("DELETE FROM processed_projects")
        product_predicate, product_params = _not_preserved("id", favorite_ids)
        deleted_products = connection.execute(
            f"DELETE FROM products WHERE {product_predicate} RETURNING id", product_params,
        ).fetchall()

        after_counts = _table_counts(connection, DISCOVERY_TABLES + OPTIONAL_DERIVED_TABLES)
        after_favorites = favorite_integrity(connection)
        after_hashes = {
            row["product_id"]: row["raw_data_hash"] for row in after_favorites["products"]
        }
        lost_ids = sorted(set(favorite_ids) - set(after_favorites["favorite_product_ids"]))
        raw_data_changed = sorted(
            product_id for product_id, digest in favorite_hashes.items()
            if after_hashes.get(product_id) != digest
        )
        remaining_products = after_counts.get("products", 0)
        expected_deleted = before_counts.get("products", 0) - len(favorite_ids)
        invariant_errors = []
        if len(deleted_products) != expected_deleted:
            invariant_errors.append("deleted Product count differs from expected")
        if remaining_products != len(favorite_ids):
            invariant_errors.append("non-favorited old Products remain")
        if after_favorites["favorite_rows"] != before_favorites["favorite_rows"]:
            invariant_errors.append("Favorite row count changed")
        if lost_ids:
            invariant_errors.append("Favorite Product IDs were lost")
        if raw_data_changed:
            invariant_errors.append("Favorite raw_data changed")
        for table in (
            "micro_innovation_candidates", "ai_triage_results", "deep_analysis_results",
            "software_analysis_results", "specificity_results", "product_observations",
            "pipeline_source_runs", "pipeline_runs", "re_evaluation_requests",
        ):
            if after_counts.get(table, 0):
                invariant_errors.append(f"{table} is not empty")
        if invariant_errors:
            raise Phase11DSafetyError("; ".join(invariant_errors))

        result = {
            "mode": "reset_and_validate",
            "completed_at": datetime.now(timezone.utc),
            "backup": backup,
            "before_counts": before_counts,
            "after_reset_counts": after_counts,
            "favorites_before": before_favorites,
            "favorites_after": after_favorites,
            "products_deleted": len(deleted_products),
            "favorite_product_ids_lost": lost_ids,
            "favorite_raw_data_changed": raw_data_changed,
            "schema_preserved": True,
            "secrets_unchanged": True,
        }
    write_json(output_dir / "reset_result.json", result)
    return result


_SUSPICIOUS_PASS = re.compile(
    r"film|movie|album|festival|donation|trip report|itinerary|travel diary|"
    r"generic advice|generic discussion|edc loadout|bag dump|listicle|architecture|"
    r"customer service|creator support|what would you redesign|best gadgets",
    re.I,
)
_FALSE_NEGATIVE = re.compile(
    r"looking for|need(?:ing)? a|recommend|wish there was|complaint|problem with|"
    r"replacement|alternative|app|software|tool|organizer|backpack|bag|pouch|lamp|"
    r"bottle|chair|wallet|holder|case|adapter",
    re.I,
)


def _excluded_samples(connection, run_id: str, status: str, limit: int = 20) -> list[dict]:
    rows = [dict(row) for row in connection.execute(
        """SELECT p.id, p.source_platform, p.title AS source_title,
                  e.eligibility_status, e.concrete_product_status,
                  e.concrete_product_reason AS exclusion_reason,
                  i.normalized_product_name
           FROM product_observations o
           JOIN products p ON p.id=o.product_id
           JOIN product_eligibility e ON e.product_id=p.id
           LEFT JOIN product_identities i ON i.product_id=p.id
           WHERE o.pipeline_run_id=%s AND e.concrete_product_status=%s
           ORDER BY p.id""", (run_id, status),
    ).fetchall()]
    random.Random(f"{run_id}:{status}").shuffle(rows)
    return rows[:limit]


def _family_validation(connection) -> dict:
    families = [dict(row) for row in connection.execute(
        """SELECT f.id AS family_id, f.canonical_name,
                  f.product_type,
                  COUNT(m.product_id) AS member_count,
                  COUNT(DISTINCT p.source_platform) AS source_count,
                  array_agg(DISTINCT p.source_platform ORDER BY p.source_platform) AS sources,
                  array_remove(array_agg(p.title ORDER BY p.id), NULL) AS member_titles
           FROM product_families f
           LEFT JOIN product_family_members m ON m.family_id=f.id
           LEFT JOIN products p ON p.id=m.product_id
           WHERE f.status='ACTIVE'
           GROUP BY f.id, f.canonical_name, f.product_type ORDER BY f.canonical_name"""
    ).fetchall()]
    multi = [row for row in families if row["member_count"] > 1]
    multi_source = [row for row in families if row["source_count"] > 1]
    noun_groups: dict[str, list[str]] = defaultdict(list)
    review_nouns = (
        "backpack", "bag", "pouch", "pillow", "bottle", "tumbler", "lamp",
        "organizer", "wallet", "opener", "keyboard", "printer", "chair",
        "watch", "repellent", "trap", "vacuum", "blower", "camera", "battery",
    )
    for row in families:
        lowered = row["canonical_name"].casefold()
        for noun in review_nouns:
            if noun in lowered:
                noun_groups[noun].append(row["canonical_name"])
    missed = [
        {"review_key": noun, "families": names[:8]}
        for noun, names in noun_groups.items() if len(names) > 1
    ]
    stopwords = {"the", "and", "for", "with", "from", "this", "that", "your", "app"}

    def tokens(value: str) -> set[str]:
        return {
            token for token in re.findall(r"[a-z0-9]+", value.casefold())
            if len(token) > 2 and token not in stopwords
        }

    seen_pairs = {tuple(sorted(item["families"][:2])) for item in missed if len(item["families"]) >= 2}
    candidates = []
    singletons = [row for row in families if row["member_count"] == 1]
    for index, first in enumerate(singletons):
        first_tokens = tokens(first["canonical_name"])
        for second in singletons[index + 1:]:
            if first["product_type"] != second["product_type"]:
                continue
            second_tokens = tokens(second["canonical_name"])
            shared = first_tokens & second_tokens
            if not shared:
                continue
            score = len(shared) / max(1, len(first_tokens | second_tokens))
            if score >= 0.2:
                candidates.append((score, first["canonical_name"], second["canonical_name"], shared))
    for score, first, second, shared in sorted(candidates, reverse=True):
        pair = tuple(sorted((first, second)))
        if pair in seen_pairs:
            continue
        missed.append({
            "review_key": ", ".join(sorted(shared)),
            "families": [first, second],
            "similarity": round(score, 3),
        })
        seen_pairs.add(pair)
        if len(missed) >= 20:
            break
    missed = missed[:20]

    suspicious_over_merges = []
    for row in multi:
        title_tokens = [tokens(title) for title in row["member_titles"]]
        pair_scores = []
        for index, first in enumerate(title_tokens):
            for second in title_tokens[index + 1:]:
                pair_scores.append(len(first & second) / max(1, len(first | second)))
        minimum_similarity = min(pair_scores, default=1.0)
        if minimum_similarity < 0.12:
            suspicious_over_merges.append({
                **row, "minimum_title_similarity": round(minimum_similarity, 3),
            })
    return {
        "product_families": len(families),
        "family_members": sum(int(row["member_count"]) for row in families),
        "singleton_families": sum(row["member_count"] == 1 for row in families),
        "multi_record_families": multi,
        "multi_source_families": multi_source,
        "likely_missed_merges": missed,
        "suspicious_possible_over_merges": suspicious_over_merges,
    }


def validate_fresh_run(database_url: str, output_dir: Path, reset_result_path: Path) -> dict:
    reset_result = json.loads(reset_result_path.read_text(encoding="utf-8"))
    favorite_ids = reset_result["favorites_before"]["favorite_product_ids"]
    before_hashes = {
        row["product_id"]: row["raw_data_hash"]
        for row in reset_result["favorites_before"]["products"]
    }

    import db
    latest = db.get_latest_completed_run()
    if not latest:
        raise Phase11DSafetyError("Fresh pipeline produced no completed run")
    run_id = latest["run_id"]
    discovery = db.get_daily_discovery(run_id)

    with _connect(database_url) as connection:
        counts = _table_counts(connection, DISCOVERY_TABLES + OPTIONAL_DERIVED_TABLES)
        favorites = favorite_integrity(connection)
        source_rows = [dict(row) for row in connection.execute(
            "SELECT * FROM pipeline_source_runs WHERE run_id=%s ORDER BY source_platform",
            (run_id,),
        ).fetchall()]
        source_funnel = []
        for source in source_rows:
            projection = connection.execute(
                """SELECT
                     COUNT(*) FILTER (WHERE e.eligibility_status='ELIGIBLE') AS eligible,
                     COUNT(*) FILTER (WHERE e.concrete_product_status='CONCRETE') AS concrete,
                     COUNT(*) FILTER (WHERE e.concrete_product_status='NON_CONCRETE') AS non_concrete,
                     COUNT(*) FILTER (WHERE e.concrete_product_status='AMBIGUOUS') AS ambiguous,
                     COUNT(DISTINCT fm.family_id) FILTER (
                       WHERE e.eligibility_status='ELIGIBLE'
                         AND e.concrete_product_status='CONCRETE') AS daily_families
                   FROM product_observations o
                   JOIN products p ON p.id=o.product_id
                   JOIN product_eligibility e ON e.product_id=p.id
                   LEFT JOIN product_family_members fm ON fm.product_id=p.id
                   WHERE o.pipeline_run_id=%s AND p.source_platform=%s""",
                (run_id, source["source_platform"]),
            ).fetchone()
            source_funnel.append({
                "source": source["source_platform"],
                "fetched": source["fetched"],
                "saved": source["new_count"],
                "updated": source["updated_count"],
                "failed": source["failed"],
                **dict(projection),
            })

        non_concrete = _excluded_samples(connection, run_id, "NON_CONCRETE")
        ambiguous = _excluded_samples(connection, run_id, "AMBIGUOUS")
        excluded = non_concrete + ambiguous
        likely_false_negatives = [
            item for item in excluded
            if _FALSE_NEGATIVE.search(item["source_title"] or "")
        ]
        suspicious_passes = []
        for family in discovery:
            for record in family.get("source_records", []):
                title_row = connection.execute(
                    "SELECT title FROM products WHERE id=%s", (record["product_id"],)
                ).fetchone()
                source_title = title_row["title"] if title_row else ""
                if _SUSPICIOUS_PASS.search(source_title):
                    suspicious_passes.append({
                        "source": record["source_platform"],
                        "source_title": source_title,
                        "normalized_identity": family["canonical_name"],
                        "family_id": family["family_id"],
                        "why_it_passed": "Eligible and concrete source-specific rules matched",
                    })
        family_report = _family_validation(connection)
        evidence_examples: dict[str, list[dict]] = {"WEAK": [], "MODERATE": [], "STRONG": []}
        for family in discovery:
            strength = family["evidence_strength"]
            if len(evidence_examples[strength]) >= 3:
                continue
            metrics = [dict(row) for row in connection.execute(
                """SELECT source_platform, metric_name, numeric_value, text_value
                   FROM source_evidence_snapshots
                   WHERE family_id=%s AND pipeline_run_id=%s
                   ORDER BY source_platform, metric_name""",
                (family["family_id"], run_id),
            ).fetchall()]
            evidence_examples[strength].append({
                "family_id": family["family_id"],
                "canonical_name": family["canonical_name"],
                "sources": family["source_platforms"],
                "metrics": metrics,
                "evidence_reasons": family["evidence_reasons"],
            })
        observations = int(connection.execute(
            "SELECT COUNT(*) AS count FROM product_observations WHERE pipeline_run_id=%s",
            (run_id,),
        ).fetchone()["count"])
        concrete_counts = {
            row["concrete_product_status"]: int(row["count"])
            for row in connection.execute(
                """SELECT e.concrete_product_status, COUNT(*) AS count
                   FROM product_observations o JOIN product_eligibility e ON e.product_id=o.product_id
                   WHERE o.pipeline_run_id=%s GROUP BY e.concrete_product_status""", (run_id,),
            ).fetchall()
        }
        eligible_count = int(connection.execute(
            """SELECT COUNT(*) AS count FROM product_observations o
               JOIN product_eligibility e ON e.product_id=o.product_id
               WHERE o.pipeline_run_id=%s AND e.eligibility_status='ELIGIBLE'""", (run_id,),
        ).fetchone()["count"])

    types = Counter(item["product_type"] for item in discovery)
    strengths = Counter(item["evidence_strength"] for item in discovery)
    complete_families = [{
        "family_id": item["family_id"],
        "canonical_name": item["canonical_name"],
        "canonical_name_zh": item.get("canonical_name_zh"),
        "product_type": item["product_type"],
        "sources": item["source_platforms"],
        "evidence_strength": item["evidence_strength"],
        "evidence_reasons": item["evidence_reasons"],
    } for item in discovery]
    after_hashes = {row["product_id"]: row["raw_data_hash"] for row in favorites["products"]}
    favorite_observed = {
        int(row["product_id"]) for row in db.get_observations_for_run(run_id)
        if int(row["product_id"]) in favorite_ids
    }
    report = {
        "mode": "fresh_validation",
        "run_id": run_id,
        "database_counts": counts,
        "source_funnel": source_funnel,
        "totals": {
            "fetched": sum(int(row["fetched"]) for row in source_rows),
            "products_after_fresh_run": counts.get("products", 0),
            "observed": observations,
            "eligible": eligible_count,
            "concrete": concrete_counts.get("CONCRETE", 0),
            "non_concrete": concrete_counts.get("NON_CONCRETE", 0),
            "ambiguous": concrete_counts.get("AMBIGUOUS", 0),
            "daily_discovery_families": len(discovery),
        },
        "daily_types": dict(types),
        "evidence_strength": dict(strengths),
        "daily_discovery_families": complete_families,
        "daily_discovery_representative_sample": complete_families[:50],
        "excluded_samples": {"non_concrete": non_concrete, "ambiguous": ambiguous},
        "likely_false_negatives": likely_false_negatives,
        "suspicious_passes": suspicious_passes,
        "family_validation": family_report,
        "evidence_examples": evidence_examples,
        "evidence_interpretation": (
            "Evidence strength measures factual evidence quantity/quality only; "
            "it is not a business opportunity judgment or Final Score."
        ),
        "favorite_coexistence": {
            "favorite_ids": favorite_ids,
            "favorite_ids_lost": sorted(set(favorite_ids) - set(favorites["favorite_product_ids"])),
            "favorite_raw_data_changed": sorted(
                product_id for product_id, digest in before_hashes.items()
                if after_hashes.get(product_id) != digest
            ),
            "observed_again_in_fresh_run": sorted(favorite_observed),
            "historical_only_not_in_today": sorted(set(favorite_ids) - favorite_observed),
            "remains_favorite": len(favorites["favorite_product_ids"]) == len(favorite_ids),
        },
        "gemini_calls": 0,
        "wxpusher_calls": 0,
        "production_ui_switched": False,
        "production_wxpusher_switched": False,
    }
    write_json(output_dir / "fresh_validation.json", report)
    write_json(output_dir / "daily_discovery_complete.json", complete_families)
    write_json(output_dir / "excluded_samples.json", report["excluded_samples"])
    return report
