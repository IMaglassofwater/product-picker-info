"""Small psycopg connection adapter for the existing database query surface."""

from __future__ import annotations

from contextlib import contextmanager
import json
import re
from time import perf_counter
from typing import Any, Iterator

from performance_timing import record_query


_POOLS: dict[str, Any] = {}


def _translate_sql(sql: str) -> str:
    translated = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql, flags=re.I)
    ignored = translated != sql
    translated = translated.replace("?", "%s")
    if ignored and "ON CONFLICT" not in translated.upper():
        stripped = translated.rstrip().rstrip(";")
        translated = stripped + " ON CONFLICT DO NOTHING"
    return translated


class PostgresConnectionAdapter:
    """Expose the execute API used by db.py while retaining dict-like rows."""

    def __init__(self, connection: Any):
        self.connection = connection

    def execute(self, sql: str, params: tuple | list = ()):
        started = perf_counter()
        try:
            return self.connection.execute(_translate_sql(sql), params)
        finally:
            record_query(sql, perf_counter() - started)

    def executescript(self, _script: str):
        raise NotImplementedError("PostgreSQL schema uses initialize_postgres_schema")


def _pool(database_url: str):
    pool = _POOLS.get(database_url)
    if pool is None:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        pool = ConnectionPool(
            conninfo=database_url,
            min_size=0,
            max_size=4,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        _POOLS[database_url] = pool
    return pool


@contextmanager
def postgres_connection(database_url: str) -> Iterator[PostgresConnectionAdapter]:
    """Borrow one bounded pooled connection and commit/rollback with context exit."""
    with _pool(database_url).connection() as connection:
        yield PostgresConnectionAdapter(connection)


def initialize_postgres_schema(database_url: str) -> None:
    """Create production tables and dashboard indexes idempotently."""
    with postgres_connection(database_url) as connection:
        for statement in POSTGRES_SCHEMA.split(";"):
            if statement.strip():
                connection.execute(statement)


EVIDENCE_SCHEMA_TABLES = frozenset({
    "product_observations", "product_eligibility", "product_identities",
    "product_families", "product_family_members", "source_evidence_snapshots",
    "daily_discovery_runs", "daily_discovery_items", "product_family_enrichments",
    "daily_picks_runs", "daily_picks_items", "user_voice_items",
    "product_directions", "product_direction_members", "notification_deliveries",
})


def evidence_schema_statements() -> list[str]:
    """Return only the additive Phase 11 Evidence-First DDL statements.

    Statements are selected from ``POSTGRES_SCHEMA`` so the manual deployment
    cannot drift into a second competing schema definition.
    """
    selected = []
    for statement in POSTGRES_SCHEMA.split(";"):
        cleaned = statement.strip()
        lowered = cleaned.casefold()
        if cleaned and any(re.search(rf"\b{re.escape(table)}\b", lowered) for table in EVIDENCE_SCHEMA_TABLES):
            selected.append(cleaned)
    return selected


def initialize_evidence_schema(database_url: str) -> None:
    """Deploy only the additive Evidence-First schema in one transaction."""
    with postgres_connection(database_url) as connection:
        for statement in evidence_schema_statements():
            connection.execute(statement)


PRODUCT_BATCH_COLUMNS = (
    "project_id", "source_platform", "url", "title", "description",
    "category", "image_url", "raw_data", "filter_score", "filter_status",
    "filter_reason", "opportunity_type", "feasibility_status",
    "feasibility_score", "feasibility_reason", "risk_flags",
    "positive_signals", "record_role", "demand_signal_status",
    "demand_signal_score", "demand_signal_type", "demand_signal_reason",
    "demand_opportunity_status", "demand_opportunity_score",
    "demand_opportunity_reason", "opportunity_flags", "commodity_status",
    "commodity_score", "commodity_reason", "commodity_flags",
    "first_seen_at", "last_seen_at", "updated_at",
)


def persist_product_batch(connection: PostgresConnectionAdapter, rows: list[dict]) -> tuple[int, int, int, float]:
    """Upsert one source batch and append changed metric snapshots."""
    if not rows:
        return 0, 0, 0, 0.0
    by_url: dict[str, dict] = {}
    duplicate_inputs = 0
    for row in rows:
        duplicate_inputs += int(row["url"] in by_url)
        by_url[row["url"]] = row
    batch = list(by_url.values())
    urls = list(by_url)
    existing_rows = connection.execute(
        "SELECT id, url FROM products WHERE url = ANY(%s)", (urls,),
    ).fetchall()
    existing_urls = {row["url"] for row in existing_rows}

    value_group = "(" + ",".join(["%s"] * len(PRODUCT_BATCH_COLUMNS)) + ")"
    values_sql = ",".join([value_group] * len(batch))
    update_columns = [
        name for name in PRODUCT_BATCH_COLUMNS
        if name not in {"url", "first_seen_at"}
    ]
    update_sql = ",".join(f"{name}=excluded.{name}" for name in update_columns)
    params = tuple(value for row in batch for value in row["values"])
    returned = connection.execute(
        f"""INSERT INTO products ({','.join(PRODUCT_BATCH_COLUMNS)})
            VALUES {values_sql}
            ON CONFLICT(url) DO UPDATE SET {update_sql}
            RETURNING id, url""",
        params,
    ).fetchall()
    ids = {row["url"]: row["id"] for row in returned}

    metric_rows = [row for row in batch if row["metrics"] and row["url"] in ids]
    snapshot_started = perf_counter()
    latest = {}
    if metric_rows:
        product_ids = [ids[row["url"]] for row in metric_rows]
        latest_rows = connection.execute(
            """SELECT DISTINCT ON (product_id) product_id, metric_data
               FROM product_metric_snapshots
               WHERE product_id = ANY(%s) AND metric_type = 'source_metrics'
               ORDER BY product_id, id DESC""",
            (product_ids,),
        ).fetchall()
        latest = {row["product_id"]: row["metric_data"] for row in latest_rows}

    snapshots = []
    for row in metric_rows:
        product_id = ids[row["url"]]
        metrics = row["metrics"]
        previous = latest.get(product_id)
        if isinstance(previous, str):
            try:
                previous = json.loads(previous)
            except json.JSONDecodeError:
                pass
        if previous != metrics:
            snapshots.append((
                product_id, row["source_platform"], row["captured_at"],
                json.dumps(metrics, ensure_ascii=False, sort_keys=True),
            ))
    if snapshots:
        snapshot_group = "(%s,%s,%s,'source_metrics',%s)"
        connection.execute(
            """INSERT INTO product_metric_snapshots
               (product_id, source_platform, captured_at, metric_type, metric_data)
               VALUES """ + ",".join([snapshot_group] * len(snapshots)),
            tuple(value for snapshot in snapshots for value in snapshot),
        )
    saved = sum(row["url"] not in existing_urls for row in batch)
    duplicates = len(batch) - saved + duplicate_inputs
    return saved, duplicates, len(snapshots), perf_counter() - snapshot_started


POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 project_id TEXT NOT NULL, source_platform TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
 title TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
 image_url TEXT NOT NULL, raw_data JSONB NOT NULL DEFAULT '{}'::jsonb,
 filter_score INTEGER NOT NULL DEFAULT 0, filter_status TEXT NOT NULL DEFAULT '',
 filter_reason TEXT NOT NULL DEFAULT '', opportunity_type TEXT NOT NULL DEFAULT 'uncertain',
 feasibility_status TEXT NOT NULL DEFAULT 'REVIEW', feasibility_score INTEGER NOT NULL DEFAULT 0,
 feasibility_reason TEXT NOT NULL DEFAULT '', risk_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
 positive_signals JSONB NOT NULL DEFAULT '[]'::jsonb, record_role TEXT NOT NULL DEFAULT 'uncertain',
 demand_signal_status TEXT NOT NULL DEFAULT '', demand_signal_score INTEGER NOT NULL DEFAULT 0,
 demand_signal_type TEXT NOT NULL DEFAULT '', demand_signal_reason TEXT NOT NULL DEFAULT '',
 demand_opportunity_status TEXT NOT NULL DEFAULT '', demand_opportunity_score INTEGER NOT NULL DEFAULT 0,
 demand_opportunity_reason TEXT NOT NULL DEFAULT '', opportunity_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
 commodity_status TEXT NOT NULL DEFAULT '', commodity_score INTEGER NOT NULL DEFAULT 0,
 commodity_reason TEXT NOT NULL DEFAULT '', commodity_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, first_seen_at TIMESTAMPTZ,
 last_seen_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS processed_projects (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, url TEXT NOT NULL UNIQUE,
 source_platform TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
 pushed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS micro_innovation_candidates (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, candidate_id TEXT NOT NULL UNIQUE,
 candidate_type TEXT NOT NULL, source_platform TEXT NOT NULL, source_url TEXT NOT NULL UNIQUE,
 title TEXT NOT NULL, summary TEXT NOT NULL, candidate_score INTEGER NOT NULL,
 feasibility_score INTEGER NOT NULL, demand_score INTEGER NOT NULL,
 market_validation_score INTEGER NOT NULL, micro_innovation_score INTEGER NOT NULL,
 reason TEXT NOT NULL, signals JSONB NOT NULL DEFAULT '[]'::jsonb,
 raw_reference_id TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ai_triage_results (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, candidate_id TEXT NOT NULL,
 triage_status TEXT NOT NULL, triage_score INTEGER NOT NULL, confidence TEXT NOT NULL,
 primary_reason TEXT NOT NULL, opportunity_type TEXT NOT NULL, key_opportunity TEXT NOT NULL,
 main_risks JSONB NOT NULL DEFAULT '[]'::jsonb, needs_deep_analysis BOOLEAN NOT NULL,
 provider TEXT NOT NULL, model TEXT NOT NULL, display_title_zh TEXT,
 primary_reason_zh TEXT, key_opportunity_zh TEXT, main_risks_zh JSONB NOT NULL DEFAULT '[]'::jsonb,
 analyzed_at TIMESTAMPTZ NOT NULL, UNIQUE(candidate_id, provider, model)
);
CREATE TABLE IF NOT EXISTS deep_analysis_results (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, candidate_id TEXT NOT NULL,
 provider TEXT NOT NULL, model TEXT NOT NULL, analysis_version TEXT NOT NULL,
 deep_score INTEGER NOT NULL, recommended_next_step TEXT NOT NULL, result_json JSONB NOT NULL,
 input_characters INTEGER NOT NULL, input_tokens INTEGER, output_tokens INTEGER, total_tokens INTEGER,
 created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
 UNIQUE(candidate_id, provider, model, analysis_version)
);
CREATE TABLE IF NOT EXISTS software_analysis_results (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, candidate_id TEXT NOT NULL,
 provider TEXT NOT NULL, model TEXT NOT NULL, analysis_version TEXT NOT NULL,
 software_score INTEGER NOT NULL, recommended_next_step TEXT NOT NULL, result_json JSONB NOT NULL,
 input_characters INTEGER NOT NULL, input_tokens INTEGER, output_tokens INTEGER, total_tokens INTEGER,
 created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
 UNIQUE(candidate_id, provider, model, analysis_version)
);
CREATE TABLE IF NOT EXISTS product_metric_snapshots (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 product_id BIGINT NOT NULL REFERENCES products(id), source_platform TEXT NOT NULL,
 captured_at TIMESTAMPTZ NOT NULL, metric_type TEXT NOT NULL, metric_data JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS pipeline_runs (
 run_id TEXT PRIMARY KEY, started_at TIMESTAMPTZ NOT NULL, finished_at TIMESTAMPTZ,
 status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', stats_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS stats_json JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE TABLE IF NOT EXISTS pipeline_source_runs (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
 source_platform TEXT NOT NULL, fetched INTEGER NOT NULL DEFAULT 0, new_count INTEGER NOT NULL DEFAULT 0,
 updated_count INTEGER NOT NULL DEFAULT 0, failed BOOLEAN NOT NULL DEFAULT FALSE,
 rejected INTEGER NOT NULL DEFAULT 0, candidates_created INTEGER NOT NULL DEFAULT 0,
 error TEXT NOT NULL DEFAULT '', UNIQUE(run_id, source_platform)
);
CREATE TABLE IF NOT EXISTS specificity_results (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, candidate_id TEXT NOT NULL,
 specificity_status TEXT NOT NULL, specificity_score INTEGER NOT NULL,
 specificity_reason TEXT NOT NULL, specificity_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
 rule_version TEXT NOT NULL, evaluated_at TIMESTAMPTZ NOT NULL,
 UNIQUE(candidate_id, rule_version)
);
CREATE TABLE IF NOT EXISTS user_product_feedback (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, entity_type TEXT NOT NULL,
 entity_id TEXT NOT NULL, feedback_type TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
 created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
 UNIQUE(entity_type, entity_id)
);
CREATE TABLE IF NOT EXISTS re_evaluation_requests (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, entity_type TEXT NOT NULL,
 entity_id TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'PENDING',
 created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS product_eligibility (
 product_id BIGINT PRIMARY KEY REFERENCES products(id), content_type TEXT NOT NULL,
 eligibility_status TEXT NOT NULL, eligibility_reason TEXT NOT NULL,
 eligibility_version TEXT NOT NULL,
 concrete_product_status TEXT NOT NULL DEFAULT 'AMBIGUOUS',
 concrete_product_reason TEXT NOT NULL DEFAULT '',
 concrete_product_version TEXT NOT NULL DEFAULT 'concrete-v1',
 evaluated_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE product_eligibility ADD COLUMN IF NOT EXISTS concrete_product_status TEXT NOT NULL DEFAULT 'AMBIGUOUS';
ALTER TABLE product_eligibility ADD COLUMN IF NOT EXISTS concrete_product_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE product_eligibility ADD COLUMN IF NOT EXISTS concrete_product_version TEXT NOT NULL DEFAULT 'concrete-v1';
CREATE TABLE IF NOT EXISTS product_identities (
 product_id BIGINT PRIMARY KEY REFERENCES products(id), source_title TEXT NOT NULL,
 normalized_product_name TEXT, normalized_product_name_zh TEXT,
 normalization_method TEXT NOT NULL, normalization_confidence TEXT NOT NULL,
 normalization_version TEXT NOT NULL, normalized_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS product_families (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, family_key TEXT NOT NULL UNIQUE,
 canonical_name TEXT NOT NULL, canonical_name_zh TEXT, primary_category TEXT NOT NULL DEFAULT '',
 product_type TEXT NOT NULL, first_seen_at TIMESTAMPTZ NOT NULL, last_seen_at TIMESTAMPTZ NOT NULL,
 status TEXT NOT NULL DEFAULT 'ACTIVE', grouping_version TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS product_family_members (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 family_id BIGINT NOT NULL REFERENCES product_families(id),
 product_id BIGINT NOT NULL UNIQUE REFERENCES products(id), match_method TEXT NOT NULL,
 match_score DOUBLE PRECISION NOT NULL, reviewed BOOLEAN NOT NULL DEFAULT FALSE,
 manual_override BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS product_observations (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 pipeline_run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
 product_id BIGINT NOT NULL REFERENCES products(id), observed_at TIMESTAMPTZ NOT NULL,
 source_platform TEXT NOT NULL, was_new BOOLEAN NOT NULL DEFAULT FALSE,
 was_updated BOOLEAN NOT NULL DEFAULT FALSE, evidence_snapshot_id BIGINT,
 created_at TIMESTAMPTZ NOT NULL, UNIQUE(pipeline_run_id, product_id)
);
CREATE TABLE IF NOT EXISTS source_evidence_snapshots (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 product_id BIGINT NOT NULL REFERENCES products(id),
 family_id BIGINT REFERENCES product_families(id), pipeline_run_id TEXT REFERENCES pipeline_runs(run_id),
 source_platform TEXT NOT NULL, observed_at TIMESTAMPTZ NOT NULL,
 evidence_type TEXT NOT NULL, metric_name TEXT NOT NULL,
 numeric_value DOUBLE PRECISION, text_value TEXT, raw_reference JSONB NOT NULL DEFAULT '{}'::jsonb,
 evidence_version TEXT NOT NULL, evidence_key TEXT NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_discovery_runs (
 run_id TEXT PRIMARY KEY, pipeline_run_id TEXT NOT NULL UNIQUE REFERENCES pipeline_runs(run_id),
 discovery_date DATE NOT NULL, generated_at TIMESTAMPTZ NOT NULL, status TEXT NOT NULL,
 item_count INTEGER NOT NULL DEFAULT 0, metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS daily_discovery_items (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 daily_run_id TEXT NOT NULL REFERENCES daily_discovery_runs(run_id),
 family_id BIGINT NOT NULL REFERENCES product_families(id), display_order INTEGER NOT NULL,
 canonical_name TEXT NOT NULL, canonical_name_zh TEXT, product_type TEXT NOT NULL,
 evidence_strength TEXT NOT NULL, snapshot_json JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL,
 UNIQUE(daily_run_id,family_id), UNIQUE(daily_run_id,display_order)
);
CREATE TABLE IF NOT EXISTS product_family_enrichments (
 family_id BIGINT PRIMARY KEY REFERENCES product_families(id),
 identity_fingerprint TEXT NOT NULL, canonical_name_en TEXT NOT NULL,
 canonical_name_zh TEXT NOT NULL, factual_description_zh TEXT NOT NULL,
 enrichment_version TEXT NOT NULL, status TEXT NOT NULL,
 error_type TEXT NOT NULL DEFAULT '', generated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_picks_runs (
 run_id TEXT PRIMARY KEY, daily_discovery_run_id TEXT NOT NULL UNIQUE REFERENCES daily_discovery_runs(run_id),
 generated_at TIMESTAMPTZ NOT NULL, target_count INTEGER NOT NULL, item_count INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL, metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS product_directions (
 direction_id TEXT PRIMARY KEY, direction_key TEXT NOT NULL UNIQUE,
 name_en TEXT NOT NULL, name_zh TEXT NOT NULL, description_zh TEXT NOT NULL,
 direction_type TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS product_direction_members (
 direction_id TEXT NOT NULL REFERENCES product_directions(direction_id),
 family_id BIGINT NOT NULL REFERENCES product_families(id), match_reason TEXT NOT NULL,
 match_confidence TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(direction_id,family_id)
);
CREATE TABLE IF NOT EXISTS daily_picks_items (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 picks_run_id TEXT NOT NULL REFERENCES daily_picks_runs(run_id),
 family_id BIGINT NOT NULL REFERENCES product_families(id), pick_order INTEGER NOT NULL,
 direction_id TEXT REFERENCES product_directions(direction_id),
 snapshot_json JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL,
 UNIQUE(picks_run_id,family_id), UNIQUE(picks_run_id,pick_order)
);
CREATE TABLE IF NOT EXISTS user_voice_items (
 id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 product_family_id BIGINT NOT NULL REFERENCES product_families(id), product_id BIGINT REFERENCES products(id),
 source TEXT NOT NULL, source_item_id TEXT, author TEXT, original_text TEXT NOT NULL,
 original_language TEXT NOT NULL DEFAULT 'unknown', source_url TEXT NOT NULL,
 published_at TIMESTAMPTZ, engagement_json JSONB NOT NULL DEFAULT '{}'::jsonb,
 retrieved_at TIMESTAMPTZ NOT NULL, voice_type TEXT NOT NULL DEFAULT 'OTHER_DISCUSSION',
 identity_key TEXT NOT NULL UNIQUE, product_direction_id TEXT REFERENCES product_directions(direction_id),
 translated_text_zh TEXT, score_or_likes TEXT, source_post_id TEXT, source_comment_id TEXT,
 parent_feedback_id TEXT, retrieval_method TEXT, traceable BOOLEAN NOT NULL DEFAULT TRUE,
 is_platform_ai_summary BOOLEAN NOT NULL DEFAULT FALSE, content_hash TEXT,
 metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
ALTER TABLE daily_picks_items ADD COLUMN IF NOT EXISTS direction_id TEXT REFERENCES product_directions(direction_id);
ALTER TABLE user_voice_items ADD COLUMN IF NOT EXISTS product_direction_id TEXT REFERENCES product_directions(direction_id);
ALTER TABLE user_voice_items ADD COLUMN IF NOT EXISTS translated_text_zh TEXT;
ALTER TABLE user_voice_items ADD COLUMN IF NOT EXISTS score_or_likes TEXT;
ALTER TABLE user_voice_items ADD COLUMN IF NOT EXISTS source_post_id TEXT;
ALTER TABLE user_voice_items ADD COLUMN IF NOT EXISTS source_comment_id TEXT;
ALTER TABLE user_voice_items ADD COLUMN IF NOT EXISTS parent_feedback_id TEXT;
ALTER TABLE user_voice_items ADD COLUMN IF NOT EXISTS retrieval_method TEXT;
ALTER TABLE user_voice_items ADD COLUMN IF NOT EXISTS traceable BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE user_voice_items ADD COLUMN IF NOT EXISTS is_platform_ai_summary BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE user_voice_items ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE user_voice_items ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE TABLE IF NOT EXISTS notification_deliveries (
 delivery_key TEXT PRIMARY KEY, daily_run_id TEXT NOT NULL, channel TEXT NOT NULL,
 recipient_hash TEXT NOT NULL, status TEXT NOT NULL, chunk_count INTEGER NOT NULL,
 delivered_chunks INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_products_source ON products(source_platform);
CREATE INDEX IF NOT EXISTS idx_products_first_seen ON products(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_products_last_seen ON products(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_products_filter_status ON products(filter_status);
CREATE INDEX IF NOT EXISTS idx_products_feasibility_status ON products(feasibility_status);
CREATE INDEX IF NOT EXISTS idx_products_commodity_status ON products(commodity_status);
CREATE INDEX IF NOT EXISTS idx_triage_candidate_provider_model ON ai_triage_results(candidate_id, provider, model);
CREATE INDEX IF NOT EXISTS idx_feedback_entity ON user_product_feedback(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_observations_run ON product_observations(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_family_members_family ON product_family_members(family_id);
CREATE INDEX IF NOT EXISTS idx_evidence_product ON source_evidence_snapshots(product_id);
CREATE INDEX IF NOT EXISTS idx_daily_discovery_date ON daily_discovery_runs(discovery_date);
CREATE INDEX IF NOT EXISTS idx_daily_discovery_items_run ON daily_discovery_items(daily_run_id,display_order);
CREATE INDEX IF NOT EXISTS idx_family_enrichment_fingerprint ON product_family_enrichments(identity_fingerprint);
CREATE INDEX IF NOT EXISTS idx_daily_picks_items_run ON daily_picks_items(picks_run_id,pick_order);
CREATE INDEX IF NOT EXISTS idx_user_voice_family ON user_voice_items(product_family_id);
"""
