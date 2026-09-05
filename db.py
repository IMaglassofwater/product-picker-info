"""SQLite persistence for products and processed project URLs."""

import json
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from pathlib import Path

from candidate_pool import MicroInnovationCandidate
from commodity_filter import CommodityResult
from demand_signal_filter import DemandSignalResult, RecordRoleResult
from demand_opportunity_filter import DemandOpportunityResult
from deep_analysis import DeepAnalysisResult
from feasibility_filter import FeasibilityResult
from models import AITriageResult, Product
from rule_filter import FilterResult
from software_analysis import SoftwareAnalysisResult
from opportunity_specificity import SpecificityResult
from database_backend import DEFAULT_SQLITE_PATH, get_database_settings
from performance_timing import timing_line


DATABASE_SETTINGS = get_database_settings()
DB_PATH = DATABASE_SETTINGS.sqlite_path or DEFAULT_SQLITE_PATH
_INITIALIZED_POSTGRES_DATABASES: set[str] = set()
_POSTGRES_STATEMENT_TIMEOUT_MS: ContextVar[int | None] = ContextVar(
    "postgres_statement_timeout_ms", default=None,
)


def _decode_json(value, default):
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value) if value else default


def _text_timestamp(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def _connect() -> sqlite3.Connection:
    if DATABASE_SETTINGS.backend == "postgresql":
        from postgres_backend import postgres_connection
        return postgres_connection(
            DATABASE_SETTINGS.database_url,
            statement_timeout_ms=_POSTGRES_STATEMENT_TIMEOUT_MS.get(),
        )
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def bounded_postgres_statements(timeout_seconds: float | None):
    """Bound each PostgreSQL statement for one orchestration stage.

    SQLite remains unchanged. The ContextVar makes nested DB helpers inherit
    the bound without changing their public APIs or leaking it to other runs.
    """
    timeout_ms = None
    if timeout_seconds is not None and DATABASE_SETTINGS.backend == "postgresql":
        timeout_ms = max(1, int(float(timeout_seconds) * 1000))
    token = _POSTGRES_STATEMENT_TIMEOUT_MS.set(timeout_ms)
    try:
        yield
    finally:
        _POSTGRES_STATEMENT_TIMEOUT_MS.reset(token)


def init_db() -> bool:
    """Create the database directory and required tables."""
    try:
        if DATABASE_SETTINGS.backend == "postgresql":
            database_url = DATABASE_SETTINGS.database_url
            if database_url in _INITIALIZED_POSTGRES_DATABASES:
                return True
            from postgres_backend import initialize_postgres_schema
            initialize_postgres_schema(database_url)
            _INITIALIZED_POSTGRES_DATABASES.add(database_url)
            return True
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    source_platform TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    image_url TEXT NOT NULL,
                    raw_data TEXT NOT NULL,
                    filter_score INTEGER NOT NULL DEFAULT 0,
                    filter_status TEXT NOT NULL DEFAULT '',
                    filter_reason TEXT NOT NULL DEFAULT '',
                    opportunity_type TEXT NOT NULL DEFAULT 'uncertain',
                    feasibility_status TEXT NOT NULL DEFAULT 'REVIEW',
                    feasibility_score INTEGER NOT NULL DEFAULT 0,
                    feasibility_reason TEXT NOT NULL DEFAULT '',
                    risk_flags TEXT NOT NULL DEFAULT '[]',
                    positive_signals TEXT NOT NULL DEFAULT '[]',
                    record_role TEXT NOT NULL DEFAULT 'uncertain',
                    demand_signal_status TEXT NOT NULL DEFAULT '',
                    demand_signal_score INTEGER NOT NULL DEFAULT 0,
                    demand_signal_type TEXT NOT NULL DEFAULT '',
                    demand_signal_reason TEXT NOT NULL DEFAULT '',
                    demand_opportunity_status TEXT NOT NULL DEFAULT '',
                    demand_opportunity_score INTEGER NOT NULL DEFAULT 0,
                    demand_opportunity_reason TEXT NOT NULL DEFAULT '',
                    opportunity_flags TEXT NOT NULL DEFAULT '[]',
                    commodity_status TEXT NOT NULL DEFAULT '',
                    commodity_score INTEGER NOT NULL DEFAULT 0,
                    commodity_reason TEXT NOT NULL DEFAULT '',
                    commodity_flags TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS processed_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    source_platform TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    pushed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS micro_innovation_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL UNIQUE,
                    candidate_type TEXT NOT NULL,
                    source_platform TEXT NOT NULL,
                    source_url TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    candidate_score INTEGER NOT NULL,
                    feasibility_score INTEGER NOT NULL,
                    demand_score INTEGER NOT NULL,
                    market_validation_score INTEGER NOT NULL,
                    micro_innovation_score INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    signals TEXT NOT NULL,
                    raw_reference_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS ai_triage_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL,
                    triage_status TEXT NOT NULL,
                    triage_score INTEGER NOT NULL,
                    confidence TEXT NOT NULL,
                    primary_reason TEXT NOT NULL,
                    opportunity_type TEXT NOT NULL,
                    key_opportunity TEXT NOT NULL,
                    main_risks TEXT NOT NULL,
                    needs_deep_analysis INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    display_title_zh TEXT,
                    primary_reason_zh TEXT,
                    key_opportunity_zh TEXT,
                    main_risks_zh TEXT NOT NULL DEFAULT '[]',
                    analyzed_at TEXT NOT NULL,
                    UNIQUE(candidate_id, provider, model)
                );

                CREATE TABLE IF NOT EXISTS deep_analysis_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    analysis_version TEXT NOT NULL,
                    deep_score INTEGER NOT NULL,
                    recommended_next_step TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    input_characters INTEGER NOT NULL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    total_tokens INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(candidate_id, provider, model, analysis_version)
                );

                CREATE TABLE IF NOT EXISTS software_analysis_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    analysis_version TEXT NOT NULL,
                    software_score INTEGER NOT NULL,
                    recommended_next_step TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    input_characters INTEGER NOT NULL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    total_tokens INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(candidate_id, provider, model, analysis_version)
                );

                CREATE TABLE IF NOT EXISTS product_metric_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    source_platform TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    metric_type TEXT NOT NULL,
                    metric_data TEXT NOT NULL,
                    FOREIGN KEY(product_id) REFERENCES products(id)
                );

                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    stats_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS pipeline_source_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    source_platform TEXT NOT NULL,
                    fetched INTEGER NOT NULL DEFAULT 0,
                    new_count INTEGER NOT NULL DEFAULT 0,
                    updated_count INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    rejected INTEGER NOT NULL DEFAULT 0,
                    candidates_created INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    UNIQUE(run_id, source_platform),
                    FOREIGN KEY(run_id) REFERENCES pipeline_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS specificity_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL,
                    specificity_status TEXT NOT NULL,
                    specificity_score INTEGER NOT NULL,
                    specificity_reason TEXT NOT NULL,
                    specificity_flags TEXT NOT NULL DEFAULT '[]',
                    rule_version TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    UNIQUE(candidate_id, rule_version)
                );

                CREATE TABLE IF NOT EXISTS user_product_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    feedback_type TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(entity_type, entity_id)
                );

                CREATE TABLE IF NOT EXISTS re_evaluation_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS product_eligibility (
                    product_id INTEGER PRIMARY KEY,
                    content_type TEXT NOT NULL,
                    eligibility_status TEXT NOT NULL,
                    eligibility_reason TEXT NOT NULL,
                    eligibility_version TEXT NOT NULL,
                    concrete_product_status TEXT NOT NULL DEFAULT 'AMBIGUOUS',
                    concrete_product_reason TEXT NOT NULL DEFAULT '',
                    concrete_product_version TEXT NOT NULL DEFAULT 'concrete-v1',
                    evaluated_at TEXT NOT NULL,
                    FOREIGN KEY(product_id) REFERENCES products(id)
                );

                CREATE TABLE IF NOT EXISTS product_identities (
                    product_id INTEGER PRIMARY KEY,
                    source_title TEXT NOT NULL,
                    normalized_product_name TEXT,
                    normalized_product_name_zh TEXT,
                    normalization_method TEXT NOT NULL,
                    normalization_confidence TEXT NOT NULL,
                    normalization_version TEXT NOT NULL,
                    normalized_at TEXT NOT NULL,
                    FOREIGN KEY(product_id) REFERENCES products(id)
                );

                CREATE TABLE IF NOT EXISTS product_families (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_key TEXT NOT NULL UNIQUE,
                    canonical_name TEXT NOT NULL,
                    canonical_name_zh TEXT,
                    primary_category TEXT NOT NULL DEFAULT '',
                    product_type TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    grouping_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS product_family_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL UNIQUE,
                    match_method TEXT NOT NULL,
                    match_score REAL NOT NULL,
                    reviewed INTEGER NOT NULL DEFAULT 0,
                    manual_override INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(family_id) REFERENCES product_families(id),
                    FOREIGN KEY(product_id) REFERENCES products(id)
                );

                CREATE TABLE IF NOT EXISTS product_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pipeline_run_id TEXT NOT NULL,
                    product_id INTEGER NOT NULL,
                    observed_at TEXT NOT NULL,
                    source_platform TEXT NOT NULL,
                    was_new INTEGER NOT NULL DEFAULT 0,
                    was_updated INTEGER NOT NULL DEFAULT 0,
                    evidence_snapshot_id INTEGER,
                    created_at TEXT NOT NULL,
                    UNIQUE(pipeline_run_id, product_id),
                    FOREIGN KEY(pipeline_run_id) REFERENCES pipeline_runs(run_id),
                    FOREIGN KEY(product_id) REFERENCES products(id)
                );

                CREATE TABLE IF NOT EXISTS source_evidence_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    family_id INTEGER,
                    pipeline_run_id TEXT,
                    source_platform TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    numeric_value REAL,
                    text_value TEXT,
                    raw_reference TEXT NOT NULL DEFAULT '{}',
                    evidence_version TEXT NOT NULL,
                    evidence_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(product_id) REFERENCES products(id),
                    FOREIGN KEY(family_id) REFERENCES product_families(id),
                    FOREIGN KEY(pipeline_run_id) REFERENCES pipeline_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS daily_discovery_runs (
                    run_id TEXT PRIMARY KEY,
                    pipeline_run_id TEXT NOT NULL UNIQUE,
                    discovery_date TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    item_count INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(pipeline_run_id) REFERENCES pipeline_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS daily_discovery_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    daily_run_id TEXT NOT NULL,
                    family_id INTEGER NOT NULL,
                    display_order INTEGER NOT NULL,
                    canonical_name TEXT NOT NULL,
                    canonical_name_zh TEXT,
                    product_type TEXT NOT NULL,
                    evidence_strength TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(daily_run_id, family_id),
                    UNIQUE(daily_run_id, display_order),
                    FOREIGN KEY(daily_run_id) REFERENCES daily_discovery_runs(run_id),
                    FOREIGN KEY(family_id) REFERENCES product_families(id)
                );

                CREATE TABLE IF NOT EXISTS product_family_enrichments (
                    family_id INTEGER PRIMARY KEY,
                    identity_fingerprint TEXT NOT NULL,
                    canonical_name_en TEXT NOT NULL,
                    canonical_name_zh TEXT NOT NULL,
                    factual_description_zh TEXT NOT NULL,
                    enrichment_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_type TEXT NOT NULL DEFAULT '',
                    generated_at TEXT NOT NULL,
                    FOREIGN KEY(family_id) REFERENCES product_families(id)
                );

                CREATE TABLE IF NOT EXISTS daily_picks_runs (
                    run_id TEXT PRIMARY KEY,
                    daily_discovery_run_id TEXT NOT NULL UNIQUE,
                    generated_at TEXT NOT NULL,
                    target_count INTEGER NOT NULL,
                    item_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(daily_discovery_run_id) REFERENCES daily_discovery_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS product_directions (
                    direction_id TEXT PRIMARY KEY, direction_key TEXT NOT NULL UNIQUE,
                    name_en TEXT NOT NULL, name_zh TEXT NOT NULL, description_zh TEXT NOT NULL,
                    direction_type TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS product_direction_members (
                    direction_id TEXT NOT NULL, family_id INTEGER NOT NULL,
                    match_reason TEXT NOT NULL, match_confidence TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(direction_id, family_id),
                    FOREIGN KEY(direction_id) REFERENCES product_directions(direction_id),
                    FOREIGN KEY(family_id) REFERENCES product_families(id)
                );

                CREATE TABLE IF NOT EXISTS daily_picks_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    picks_run_id TEXT NOT NULL,
                    family_id INTEGER NOT NULL,
                    pick_order INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(picks_run_id, family_id),
                    UNIQUE(picks_run_id, pick_order),
                    FOREIGN KEY(picks_run_id) REFERENCES daily_picks_runs(run_id),
                    FOREIGN KEY(family_id) REFERENCES product_families(id)
                );

                CREATE TABLE IF NOT EXISTS user_voice_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_family_id INTEGER NOT NULL,
                    product_id INTEGER,
                    source TEXT NOT NULL,
                    source_item_id TEXT,
                    author TEXT,
                    original_text TEXT NOT NULL,
                    original_language TEXT NOT NULL DEFAULT 'unknown',
                    source_url TEXT NOT NULL,
                    published_at TEXT,
                    engagement_json TEXT NOT NULL DEFAULT '{}',
                    retrieved_at TEXT NOT NULL,
                    voice_type TEXT NOT NULL DEFAULT 'OTHER_DISCUSSION',
                    identity_key TEXT NOT NULL UNIQUE,
                    FOREIGN KEY(product_family_id) REFERENCES product_families(id),
                    FOREIGN KEY(product_id) REFERENCES products(id)
                );

                CREATE TABLE IF NOT EXISTS notification_deliveries (
                    delivery_key TEXT PRIMARY KEY, daily_run_id TEXT NOT NULL, channel TEXT NOT NULL,
                    recipient_hash TEXT NOT NULL, status TEXT NOT NULL, chunk_count INTEGER NOT NULL,
                    delivered_chunks INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_observations_run ON product_observations(pipeline_run_id);
                CREATE INDEX IF NOT EXISTS idx_family_members_family ON product_family_members(family_id);
                CREATE INDEX IF NOT EXISTS idx_evidence_product ON source_evidence_snapshots(product_id);
                CREATE INDEX IF NOT EXISTS idx_daily_discovery_date ON daily_discovery_runs(discovery_date);
                CREATE INDEX IF NOT EXISTS idx_daily_discovery_items_run ON daily_discovery_items(daily_run_id, display_order);
                CREATE INDEX IF NOT EXISTS idx_family_enrichment_fingerprint ON product_family_enrichments(identity_fingerprint);
                CREATE INDEX IF NOT EXISTS idx_daily_picks_items_run ON daily_picks_items(picks_run_id, pick_order);
                CREATE INDEX IF NOT EXISTS idx_user_voice_family ON user_voice_items(product_family_id);
                """
            )
            _ensure_filter_columns(connection)
            _ensure_lifecycle_columns(connection)
            _ensure_triage_unique_key(connection)
            _ensure_triage_bilingual_columns(connection)
            _ensure_pipeline_stats_column(connection)
            _ensure_shadow_columns(connection)
            _ensure_direction_columns(connection)
        return True
    except (OSError, sqlite3.Error):
        return False


def _ensure_direction_columns(connection: sqlite3.Connection) -> None:
    """Add full-fidelity Daily Direction columns without rewriting history."""
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(daily_picks_items)")}
    if "direction_id" not in columns:
        connection.execute("ALTER TABLE daily_picks_items ADD COLUMN direction_id TEXT")
    voice_columns = {row["name"] for row in connection.execute("PRAGMA table_info(user_voice_items)")}
    additions = {"product_direction_id":"TEXT", "translated_text_zh":"TEXT", "score_or_likes":"TEXT",
        "source_post_id":"TEXT", "source_comment_id":"TEXT", "parent_feedback_id":"TEXT",
        "retrieval_method":"TEXT", "traceable":"INTEGER NOT NULL DEFAULT 1",
        "is_platform_ai_summary":"INTEGER NOT NULL DEFAULT 0", "content_hash":"TEXT",
        "metadata_json":"TEXT NOT NULL DEFAULT '{}'"}
    for name, definition in additions.items():
        if name not in voice_columns:
            connection.execute(f"ALTER TABLE user_voice_items ADD COLUMN {name} {definition}")


def _ensure_filter_columns(connection: sqlite3.Connection) -> None:
    """Add missing result columns to an existing table without data loss."""
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(products)").fetchall()
    }
    column_definitions = {
        "filter_score": "INTEGER NOT NULL DEFAULT 0",
        "filter_status": "TEXT NOT NULL DEFAULT ''",
        "filter_reason": "TEXT NOT NULL DEFAULT ''",
        "opportunity_type": "TEXT NOT NULL DEFAULT 'uncertain'",
        "feasibility_status": "TEXT NOT NULL DEFAULT 'REVIEW'",
        "feasibility_score": "INTEGER NOT NULL DEFAULT 0",
        "feasibility_reason": "TEXT NOT NULL DEFAULT ''",
        "risk_flags": "TEXT NOT NULL DEFAULT '[]'",
        "positive_signals": "TEXT NOT NULL DEFAULT '[]'",
        "record_role": "TEXT NOT NULL DEFAULT 'uncertain'",
        "demand_signal_status": "TEXT NOT NULL DEFAULT ''",
        "demand_signal_score": "INTEGER NOT NULL DEFAULT 0",
        "demand_signal_type": "TEXT NOT NULL DEFAULT ''",
        "demand_signal_reason": "TEXT NOT NULL DEFAULT ''",
        "demand_opportunity_status": "TEXT NOT NULL DEFAULT ''",
        "demand_opportunity_score": "INTEGER NOT NULL DEFAULT 0",
        "demand_opportunity_reason": "TEXT NOT NULL DEFAULT ''",
        "opportunity_flags": "TEXT NOT NULL DEFAULT '[]'",
        "commodity_status": "TEXT NOT NULL DEFAULT ''",
        "commodity_score": "INTEGER NOT NULL DEFAULT 0",
        "commodity_reason": "TEXT NOT NULL DEFAULT ''",
        "commodity_flags": "TEXT NOT NULL DEFAULT '[]'",
    }
    for column_name, definition in column_definitions.items():
        if column_name not in existing_columns:
            connection.execute(
                f"ALTER TABLE products ADD COLUMN {column_name} {definition}"
            )


def _ensure_pipeline_stats_column(connection: sqlite3.Connection) -> None:
    existing = {row["name"] for row in connection.execute("PRAGMA table_info(pipeline_runs)")}
    if "stats_json" not in existing:
        connection.execute(
            "ALTER TABLE pipeline_runs ADD COLUMN stats_json TEXT NOT NULL DEFAULT '{}'"
        )


def _ensure_shadow_columns(connection: sqlite3.Connection) -> None:
    """Add Phase 11C concrete-product fields to an existing Shadow table."""
    existing = {
        row["name"] for row in connection.execute("PRAGMA table_info(product_eligibility)")
    }
    definitions = {
        "concrete_product_status": "TEXT NOT NULL DEFAULT 'AMBIGUOUS'",
        "concrete_product_reason": "TEXT NOT NULL DEFAULT ''",
        "concrete_product_version": "TEXT NOT NULL DEFAULT 'concrete-v1'",
    }
    for name, definition in definitions.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE product_eligibility ADD COLUMN {name} {definition}")


def _ensure_lifecycle_columns(connection: sqlite3.Connection) -> None:
    """Idempotently add observation timestamps and backfill legacy rows."""
    existing = {
        row["name"] for row in connection.execute("PRAGMA table_info(products)")
    }
    for name in ("first_seen_at", "last_seen_at", "updated_at"):
        if name not in existing:
            connection.execute(f"ALTER TABLE products ADD COLUMN {name} TEXT")
    connection.execute(
        """UPDATE products
           SET first_seen_at = COALESCE(first_seen_at, created_at),
               last_seen_at = COALESCE(last_seen_at, created_at),
               updated_at = COALESCE(updated_at, created_at)
           WHERE first_seen_at IS NULL OR last_seen_at IS NULL OR updated_at IS NULL"""
    )


def _ensure_triage_unique_key(connection: sqlite3.Connection) -> None:
    """Safely migrate legacy candidate-only uniqueness without losing results."""
    unique_columns = []
    for index in connection.execute("PRAGMA index_list(ai_triage_results)").fetchall():
        if index["unique"]:
            columns = tuple(
                row["name"] for row in connection.execute(
                    f"PRAGMA index_info('{index['name']}')"
                ).fetchall()
            )
            unique_columns.append(columns)
    if unique_columns == [("candidate_id", "provider", "model")]:
        return
    old_count = connection.execute(
        "SELECT COUNT(*) FROM ai_triage_results"
    ).fetchone()[0]
    connection.execute("DROP TABLE IF EXISTS ai_triage_results_new")
    connection.execute(
        """CREATE TABLE ai_triage_results_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            triage_status TEXT NOT NULL,
            triage_score INTEGER NOT NULL,
            confidence TEXT NOT NULL,
            primary_reason TEXT NOT NULL,
            opportunity_type TEXT NOT NULL,
            key_opportunity TEXT NOT NULL,
            main_risks TEXT NOT NULL,
            needs_deep_analysis INTEGER NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            analyzed_at TEXT NOT NULL,
            UNIQUE(candidate_id, provider, model)
        )"""
    )
    connection.execute(
        """INSERT INTO ai_triage_results_new (
            id, candidate_id, triage_status, triage_score, confidence,
            primary_reason, opportunity_type, key_opportunity, main_risks,
            needs_deep_analysis, provider, model, analyzed_at
        ) SELECT id, candidate_id, triage_status, triage_score, confidence,
                 primary_reason, opportunity_type, key_opportunity, main_risks,
                 needs_deep_analysis, provider, model, analyzed_at
          FROM ai_triage_results"""
    )
    new_count = connection.execute(
        "SELECT COUNT(*) FROM ai_triage_results_new"
    ).fetchone()[0]
    if new_count != old_count:
        raise sqlite3.IntegrityError("AI triage migration count mismatch")
    connection.execute("DROP TABLE ai_triage_results")
    connection.execute("ALTER TABLE ai_triage_results_new RENAME TO ai_triage_results")


def _ensure_triage_bilingual_columns(connection: sqlite3.Connection) -> None:
    """Add nullable bilingual fields without rewriting historical triage rows."""
    existing = {row["name"] for row in connection.execute("PRAGMA table_info(ai_triage_results)")}
    definitions = {
        "display_title_zh": "TEXT",
        "primary_reason_zh": "TEXT",
        "key_opportunity_zh": "TEXT",
        "main_risks_zh": "TEXT NOT NULL DEFAULT '[]'",
    }
    for name, definition in definitions.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE ai_triage_results ADD COLUMN {name} {definition}")


def create_product(product: Product) -> bool:
    """Save one product; duplicates refresh lifecycle/data but return False."""
    saved_count, _duplicate_count = save_products([product])
    return saved_count == 1


def save_products(
    products: list[Product],
    filter_results: dict[str, FilterResult] | None = None,
    feasibility_results: dict[str, FeasibilityResult] | None = None,
    record_role_results: dict[str, RecordRoleResult] | None = None,
    demand_signal_results: dict[str, DemandSignalResult] | None = None,
    demand_opportunity_results: dict[str, DemandOpportunityResult] | None = None,
    commodity_results: dict[str, CommodityResult] | None = None,
    timing_output=None,
    initialize: bool = True,
) -> tuple[int, int]:
    """Save products in one transaction and count URL duplicates.

    Returns:
        A ``(saved_count, duplicate_count)`` tuple. Database or serialization
        errors are contained and reported as zero saved and zero duplicates.
    """
    if initialize and not init_db():
        return 0, 0

    if DATABASE_SETTINGS.backend == "postgresql":
        return _save_products_postgres_batch(
            products, filter_results, feasibility_results, record_role_results,
            demand_signal_results, demand_opportunity_results, commodity_results,
            timing_output,
        )

    saved_count = 0
    duplicate_count = 0
    snapshot_duration = 0.0
    snapshot_writes = 0
    try:
        with _connect() as connection:
            for product in products:
                now = _utc_now()
                filter_result = (filter_results or {}).get(product.url)
                filter_score = filter_result.filter_score if filter_result else 0
                filter_status = filter_result.status if filter_result else ""
                filter_reason = filter_result.reason if filter_result else ""
                opportunity_type = (
                    filter_result.opportunity_type
                    if filter_result
                    else "uncertain"
                )
                role_result = (record_role_results or {}).get(product.url)
                record_role = (
                    role_result.record_role if role_result else "uncertain"
                )
                feasibility_result = (feasibility_results or {}).get(product.url)
                feasibility_status = (
                    feasibility_result.feasibility_status
                    if feasibility_result
                    else ""
                )
                feasibility_score = (
                    feasibility_result.feasibility_score
                    if feasibility_result
                    else 0
                )
                feasibility_reason = (
                    feasibility_result.feasibility_reason
                    if feasibility_result
                    else ""
                )
                risk_flags = json.dumps(
                    feasibility_result.risk_flags if feasibility_result else []
                )
                positive_signals = json.dumps(
                    feasibility_result.positive_signals
                    if feasibility_result
                    else []
                )
                demand_result = (demand_signal_results or {}).get(product.url)
                demand_signal_status = (
                    demand_result.signal_status if demand_result else ""
                )
                demand_signal_score = (
                    demand_result.signal_score if demand_result else 0
                )
                demand_signal_type = (
                    demand_result.signal_type if demand_result else ""
                )
                demand_signal_reason = (
                    demand_result.reason if demand_result else ""
                )
                opportunity_result = (demand_opportunity_results or {}).get(
                    product.url
                )
                demand_opportunity_status = (
                    opportunity_result.demand_opportunity_status
                    if opportunity_result else ""
                )
                demand_opportunity_score = (
                    opportunity_result.demand_opportunity_score
                    if opportunity_result else 0
                )
                demand_opportunity_reason = (
                    opportunity_result.demand_opportunity_reason
                    if opportunity_result else ""
                )
                opportunity_flags = json.dumps(
                    opportunity_result.opportunity_flags
                    if opportunity_result else []
                )
                commodity_result = (commodity_results or {}).get(product.url)
                commodity_status = (
                    commodity_result.commodity_status if commodity_result else ""
                )
                commodity_score = (
                    commodity_result.commodity_score if commodity_result else 0
                )
                commodity_reason = (
                    commodity_result.commodity_reason if commodity_result else ""
                )
                commodity_flags = json.dumps(
                    commodity_result.commodity_flags if commodity_result else []
                )
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO products (
                        project_id, source_platform, url, title, description,
                        category, image_url, raw_data, filter_score,
                        filter_status, filter_reason, opportunity_type,
                        feasibility_status, feasibility_score,
                        feasibility_reason, risk_flags, positive_signals,
                        record_role,
                        demand_signal_status, demand_signal_score,
                        demand_signal_type, demand_signal_reason,
                        demand_opportunity_status, demand_opportunity_score,
                        demand_opportunity_reason, opportunity_flags,
                        commodity_status, commodity_score, commodity_reason,
                        commodity_flags, first_seen_at, last_seen_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        product.project_id,
                        product.source_platform,
                        product.url,
                        product.title,
                        product.description,
                        product.category,
                        product.image_url,
                        json.dumps(product.raw_data, ensure_ascii=False),
                        filter_score,
                        filter_status,
                        filter_reason,
                        opportunity_type,
                        feasibility_status,
                        feasibility_score,
                        feasibility_reason,
                        risk_flags,
                        positive_signals,
                        record_role,
                        demand_signal_status,
                        demand_signal_score,
                        demand_signal_type,
                        demand_signal_reason,
                        demand_opportunity_status,
                        demand_opportunity_score,
                        demand_opportunity_reason,
                        opportunity_flags,
                        commodity_status,
                        commodity_score,
                        commodity_reason,
                        commodity_flags,
                        now,
                        now,
                        now,
                    ),
                )
                if cursor.rowcount == 1:
                    saved_count += 1
                    inserted = connection.execute(
                        "SELECT id FROM products WHERE url = ?", (product.url,)
                    ).fetchone()
                    product_id = inserted["id"] if inserted else None
                else:
                    duplicate_count += 1
                    existing = connection.execute(
                        "SELECT id FROM products WHERE url = ?", (product.url,)
                    ).fetchone()
                    product_id = existing["id"] if existing else None
                    if product_id is not None:
                        connection.execute(
                            """
                            UPDATE products
                            SET project_id = ?, source_platform = ?, title = ?,
                                description = ?, category = ?, image_url = ?,
                                raw_data = ?, last_seen_at = ?, updated_at = ?,
                                filter_score = ?, filter_status = ?,
                                filter_reason = ?, opportunity_type = ?,
                                feasibility_status = ?, feasibility_score = ?,
                                feasibility_reason = ?, risk_flags = ?,
                                positive_signals = ?,
                                record_role = ?, demand_signal_status = ?,
                                demand_signal_score = ?, demand_signal_type = ?,
                                demand_signal_reason = ?,
                                demand_opportunity_status = ?,
                                demand_opportunity_score = ?,
                                demand_opportunity_reason = ?,
                                opportunity_flags = ?, commodity_status = ?,
                                commodity_score = ?, commodity_reason = ?,
                                commodity_flags = ?
                            WHERE url = ?
                            """,
                            (
                                product.project_id,
                                product.source_platform,
                                product.title,
                                product.description,
                                product.category,
                                product.image_url,
                                json.dumps(product.raw_data, ensure_ascii=False),
                                now,
                                now,
                                filter_score,
                                filter_status,
                                filter_reason,
                                opportunity_type,
                                feasibility_status,
                                feasibility_score,
                                feasibility_reason,
                                risk_flags,
                                positive_signals,
                                record_role,
                                demand_signal_status,
                                demand_signal_score,
                                demand_signal_type,
                                demand_signal_reason,
                                demand_opportunity_status,
                                demand_opportunity_score,
                                demand_opportunity_reason,
                                opportunity_flags,
                                commodity_status,
                                commodity_score,
                                commodity_reason,
                                commodity_flags,
                                product.url,
                            ),
                        )
                if product_id is not None:
                    snapshot_started = perf_counter()
                    snapshot_writes += int(_save_metric_snapshot_if_changed(
                        connection, product_id, product.source_platform,
                        product.raw_data, now,
                    ))
                    snapshot_duration += perf_counter() - snapshot_started
        if timing_output is not None:
            timing_output(timing_line(
                stage="snapshot_writes", duration_s=snapshot_duration,
                writes=snapshot_writes,
            ))
        return saved_count, duplicate_count
    except (AttributeError, TypeError, ValueError, sqlite3.Error):
        return 0, 0


def _save_products_postgres_batch(
    products, filter_results, feasibility_results, record_role_results,
    demand_signal_results, demand_opportunity_results, commodity_results,
    timing_output,
) -> tuple[int, int]:
    """Prepare and persist one PostgreSQL source batch without per-row queries."""
    from postgres_backend import persist_product_batch

    rows = []
    for product in products:
        now = _utc_now()
        filter_result = (filter_results or {}).get(product.url)
        role_result = (record_role_results or {}).get(product.url)
        feasibility = (feasibility_results or {}).get(product.url)
        demand = (demand_signal_results or {}).get(product.url)
        opportunity = (demand_opportunity_results or {}).get(product.url)
        commodity = (commodity_results or {}).get(product.url)
        values = (
            product.project_id, product.source_platform, product.url, product.title,
            product.description, product.category, product.image_url,
            json.dumps(product.raw_data, ensure_ascii=False),
            filter_result.filter_score if filter_result else 0,
            filter_result.status if filter_result else "",
            filter_result.reason if filter_result else "",
            filter_result.opportunity_type if filter_result else "uncertain",
            feasibility.feasibility_status if feasibility else "",
            feasibility.feasibility_score if feasibility else 0,
            feasibility.feasibility_reason if feasibility else "",
            json.dumps(feasibility.risk_flags if feasibility else []),
            json.dumps(feasibility.positive_signals if feasibility else []),
            role_result.record_role if role_result else "uncertain",
            demand.signal_status if demand else "",
            demand.signal_score if demand else 0,
            demand.signal_type if demand else "",
            demand.reason if demand else "",
            opportunity.demand_opportunity_status if opportunity else "",
            opportunity.demand_opportunity_score if opportunity else 0,
            opportunity.demand_opportunity_reason if opportunity else "",
            json.dumps(opportunity.opportunity_flags if opportunity else []),
            commodity.commodity_status if commodity else "",
            commodity.commodity_score if commodity else 0,
            commodity.commodity_reason if commodity else "",
            json.dumps(commodity.commodity_flags if commodity else []),
            now, now, now,
        )
        rows.append({
            "url": product.url, "values": values,
            "source_platform": product.source_platform, "captured_at": now,
            "metrics": _metric_payload(product.source_platform, product.raw_data),
        })
    try:
        with _connect() as connection:
            saved, duplicates, snapshot_writes, snapshot_duration = (
                persist_product_batch(connection, rows)
            )
        if timing_output is not None:
            timing_output(timing_line(
                stage="snapshot_writes", duration_s=snapshot_duration,
                writes=snapshot_writes,
                batched="true",
            ))
        return saved, duplicates
    except Exception:
        # The connection context rolls back the complete source batch. This
        # boundary contains driver errors so other sources can continue.
        return 0, 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metric_payload(source_platform: str, raw_data: dict) -> dict:
    source = source_platform.casefold()
    if "kickstarter" in source:
        keys = (
            "goal", "funding", "pledged", "percent_funded",
            "funding_percentage", "backers", "backers_count",
            "days_remaining", "campaign_status", "deadline",
        )
    elif "indiegogo" in source:
        keys = (
            "campaign_goal", "campaignGoal", "funding", "funds_gathered",
            "fundsGathered", "funding_percentage", "backers", "backer_count",
            "backerCount", "campaign_status", "status", "campaign_end_date",
        )
    elif "amazon" in source:
        keys = ("rank", "rating", "review_count", "price", "rank_change")
    else:
        return {}
    return {key: raw_data[key] for key in keys if raw_data.get(key) is not None}


def _save_metric_snapshot_if_changed(
    connection: sqlite3.Connection,
    product_id: int,
    source_platform: str,
    raw_data: dict,
    captured_at: str,
) -> bool:
    metrics = _metric_payload(source_platform, raw_data)
    if not metrics:
        return False
    serialized = json.dumps(metrics, ensure_ascii=False, sort_keys=True)
    previous = connection.execute(
        """SELECT metric_data FROM product_metric_snapshots
           WHERE product_id = ? AND metric_type = 'source_metrics'
           ORDER BY id DESC LIMIT 1""",
        (product_id,),
    ).fetchone()
    if previous and previous["metric_data"] == serialized:
        return False
    connection.execute(
        """INSERT INTO product_metric_snapshots
           (product_id, source_platform, captured_at, metric_type, metric_data)
           VALUES (?, ?, ?, 'source_metrics', ?)""",
        (product_id, source_platform, captured_at, serialized),
    )
    return True


def replace_candidates_by_type(
    candidate_type: str,
    candidates: list[MicroInnovationCandidate],
) -> tuple[int, int]:
    """Replace one candidate type without changing any other candidate source."""
    if not init_db():
        return 0, 0
    try:
        with _connect() as connection:
            connection.execute(
                "DELETE FROM micro_innovation_candidates WHERE candidate_type = ?",
                (candidate_type,),
            )
        return save_candidates(candidates)
    except sqlite3.Error:
        return 0, 0


def get_product_by_url(url: str) -> Product | None:
    """Return the product matching a URL, if present."""
    try:
        if not init_db():
            return None
        with _connect() as connection:
            row = connection.execute(
                """
                SELECT project_id, source_platform, url, title, description,
                       category, image_url, raw_data
                FROM products
                WHERE url = ?
                """,
                (url,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_product(row)
    except (json.JSONDecodeError, ValueError, sqlite3.Error):
        return None


def get_all_products() -> list[Product]:
    """Return every valid product currently stored in the database."""
    try:
        if not init_db():
            return []
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT project_id, source_platform, url, title, description,
                       category, image_url, raw_data
                FROM products
                ORDER BY id
                """
            ).fetchall()

        products: list[Product] = []
        for row in rows:
            try:
                products.append(_row_to_product(row))
            except (json.JSONDecodeError, ValueError):
                continue
        return products
    except sqlite3.Error:
        return []


def get_all_product_urls() -> set[str]:
    """Return every stored identity URL, including rows with legacy-invalid fields."""
    try:
        if not init_db():
            return set()
        with _connect() as connection:
            return {row["url"] for row in connection.execute("SELECT url FROM products")}
    except sqlite3.Error:
        return set()


def get_product_lifecycle(url: str) -> dict | None:
    """Return lifecycle timestamps and identity for one Product URL."""
    try:
        with _connect() as connection:
            row = connection.execute(
                """SELECT id, created_at, first_seen_at, last_seen_at, updated_at
                   FROM products WHERE url = ?""", (url,)
            ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        return None


def get_metric_snapshots(product_id: int) -> list[dict]:
    try:
        with _connect() as connection:
            rows = connection.execute(
                """SELECT id, product_id, source_platform, captured_at,
                          metric_type, metric_data
                   FROM product_metric_snapshots WHERE product_id = ? ORDER BY id""",
                (product_id,),
            ).fetchall()
        return [dict(row) | {"metric_data": _decode_json(row["metric_data"], {})} for row in rows]
    except (json.JSONDecodeError, sqlite3.Error):
        return []


def start_pipeline_run() -> str:
    run_id = uuid4().hex
    try:
        with _connect() as connection:
            connection.execute(
                "INSERT INTO pipeline_runs (run_id, started_at, status) VALUES (?, ?, 'RUNNING')",
                (run_id, _utc_now()),
            )
        return run_id
    except sqlite3.Error:
        return ""


def recover_stale_pipeline_runs(
    *, stale_after_minutes: int = 60, now: datetime | None = None,
) -> list[str]:
    """Mark clearly stale RUNNING rows failed without touching recent runs."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    recovered: list[str] = []
    try:
        with _connect() as connection:
            rows = connection.execute(
                "SELECT run_id, started_at FROM pipeline_runs WHERE status = 'RUNNING'"
            ).fetchall()
            for row in rows:
                try:
                    started = datetime.fromisoformat(
                        str(row["started_at"]).replace("Z", "+00:00")
                    )
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    continue
                if current - started <= timedelta(minutes=max(1, stale_after_minutes)):
                    continue
                cursor = connection.execute(
                    """UPDATE pipeline_runs
                       SET finished_at = ?, status = 'FAILED', error = ?
                       WHERE run_id = ? AND status = 'RUNNING'""",
                    (
                        current.isoformat(),
                        "stale run recovered after external cancellation",
                        row["run_id"],
                    ),
                )
                if cursor.rowcount == 1:
                    recovered.append(str(row["run_id"]))
        return recovered
    except Exception:
        return []


def record_pipeline_source_run(
    run_id: str,
    source_platform: str,
    *,
    fetched: int = 0,
    new_count: int = 0,
    updated_count: int = 0,
    failed: bool = False,
    rejected: int = 0,
    candidates_created: int = 0,
    error: str = "",
) -> bool:
    try:
        with _connect() as connection:
            connection.execute(
                """INSERT INTO pipeline_source_runs
                   (run_id, source_platform, fetched, new_count, updated_count,
                    failed, rejected, candidates_created, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(run_id, source_platform) DO UPDATE SET
                    fetched=excluded.fetched, new_count=excluded.new_count,
                    updated_count=excluded.updated_count, failed=excluded.failed,
                    rejected=excluded.rejected,
                    candidates_created=excluded.candidates_created,
                    error=excluded.error""",
                (run_id, source_platform, fetched, new_count, updated_count,
                 bool(failed), rejected, candidates_created, error[:1000]),
            )
        return True
    except sqlite3.Error:
        return False


def finish_pipeline_run(
    run_id: str, status: str, error: str = "", *, stats: dict | None = None
) -> bool:
    try:
        with _connect() as connection:
            cursor = connection.execute(
                """UPDATE pipeline_runs SET finished_at = ?, status = ?, error = ?, stats_json = ?
                   WHERE run_id = ?""",
                (_utc_now(), status, error[:1000], json.dumps(stats or {}, ensure_ascii=False), run_id),
            )
        return cursor.rowcount == 1
    except sqlite3.Error:
        return False


def save_specificity_result(
    candidate_id: str,
    result: SpecificityResult,
    *,
    rule_version: str = "v1",
) -> bool:
    try:
        with _connect() as connection:
            cursor = connection.execute(
                """INSERT INTO specificity_results
                   (candidate_id, specificity_status, specificity_score,
                    specificity_reason, specificity_flags, rule_version, evaluated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(candidate_id, rule_version) DO UPDATE SET
                    specificity_status=excluded.specificity_status,
                    specificity_score=excluded.specificity_score,
                    specificity_reason=excluded.specificity_reason,
                    specificity_flags=excluded.specificity_flags,
                    evaluated_at=excluded.evaluated_at""",
                (candidate_id, result.specificity_status, result.specificity_score,
                 result.specificity_reason,
                 json.dumps(result.specificity_flags, ensure_ascii=False),
                 rule_version, _utc_now()),
            )
        return cursor.rowcount == 1
    except (TypeError, ValueError, sqlite3.Error):
        return False


def save_specificity_results(
    results: list[tuple[str, SpecificityResult]], *, rule_version: str = "v1",
) -> int:
    """Save one run's specificity results in a single transaction."""
    if not results:
        return 0
    saved = 0
    try:
        with _connect() as connection:
            evaluated_at = _utc_now()
            for candidate_id, result in results:
                cursor = connection.execute(
                    """INSERT INTO specificity_results
                       (candidate_id, specificity_status, specificity_score,
                        specificity_reason, specificity_flags, rule_version, evaluated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(candidate_id, rule_version) DO UPDATE SET
                        specificity_status=excluded.specificity_status,
                        specificity_score=excluded.specificity_score,
                        specificity_reason=excluded.specificity_reason,
                        specificity_flags=excluded.specificity_flags,
                        evaluated_at=excluded.evaluated_at""",
                    (candidate_id, result.specificity_status, result.specificity_score,
                     result.specificity_reason,
                     json.dumps(result.specificity_flags, ensure_ascii=False),
                     rule_version, evaluated_at),
                )
                saved += int(cursor.rowcount == 1)
        return saved
    except (TypeError, ValueError, sqlite3.Error):
        return 0


def save_user_feedback(
    entity_type: str, entity_id: str, feedback_type: str, note: str = ""
) -> bool:
    if entity_type not in {"product", "candidate", "family"} or feedback_type not in {
        "FAVORITE", "WATCH", "NOT_INTERESTED", "HIDDEN", "DISMISSED",
    }:
        return False
    now = _utc_now()
    try:
        with _connect() as connection:
            connection.execute(
                """INSERT INTO user_product_feedback
                   (entity_type, entity_id, feedback_type, note, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                    feedback_type=excluded.feedback_type,
                    note=excluded.note, updated_at=excluded.updated_at""",
                (entity_type, entity_id, feedback_type, note, now, now),
            )
        return True
    except sqlite3.Error:
        return False


def request_re_evaluation(
    entity_type: str, entity_id: str, note: str = ""
) -> bool:
    if entity_type not in {"product", "candidate"}:
        return False
    now = _utc_now()
    try:
        with _connect() as connection:
            connection.execute(
                """INSERT INTO re_evaluation_requests
                   (entity_type, entity_id, note, status, created_at, updated_at)
                   VALUES (?, ?, ?, 'PENDING', ?, ?)""",
                (entity_type, entity_id, note, now, now),
            )
        return True
    except sqlite3.Error:
        return False


def get_pending_re_evaluations() -> list[dict]:
    """Return the durable re-evaluation queue without changing it."""
    try:
        with _connect() as connection:
            rows = connection.execute(
                """SELECT id, entity_type, entity_id, note, created_at
                   FROM re_evaluation_requests WHERE status='PENDING'
                   ORDER BY created_at, id"""
            ).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error:
        return []


def complete_re_evaluation(request_id: int) -> bool:
    try:
        with _connect() as connection:
            cursor = connection.execute(
                """UPDATE re_evaluation_requests SET status='COMPLETED', updated_at=?
                   WHERE id=? AND status='PENDING'""",
                (_utc_now(), request_id),
            )
        return cursor.rowcount == 1
    except sqlite3.Error:
        return False


# ---------------------------------------------------------------------------
# Phase 11 evidence-first shadow repository. These additive APIs intentionally
# do not alter legacy Product/Candidate/AI behavior.


def get_product_record_by_url(url: str) -> dict | None:
    """Return a complete stored Product row without changing it."""
    try:
        with _connect() as connection:
            row = connection.execute("SELECT * FROM products WHERE url = ?", (url,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["raw_data"] = _decode_json(result.get("raw_data"), {})
        return result
    except Exception:
        return None


def get_all_product_records() -> list[dict]:
    """Return all source records for deterministic shadow processing."""
    try:
        with _connect() as connection:
            rows = connection.execute("SELECT * FROM products ORDER BY id").fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["raw_data"] = _decode_json(item.get("raw_data"), {})
            output.append(item)
        return output
    except Exception:
        return []


def _product_from_record(record: dict) -> Product:
    return Product(
        project_id=record["project_id"], source_platform=record["source_platform"],
        url=record["url"], title=record["title"],
        description=record.get("description") or "", category=record["category"],
        image_url=record["image_url"], raw_data=_decode_json(record.get("raw_data"), {}),
    )


def save_shadow_product_foundation(
    product_id: int,
    product: Product,
    eligibility,
    concrete,
    identity,
    family,
    evidence_facts,
    *,
    pipeline_run_id: str | None = None,
    observed_at: str | None = None,
    was_new: bool = False,
    was_updated: bool = False,
) -> dict:
    """Persist one deterministic shadow projection in one transaction."""
    from evidence_foundation import EVIDENCE_VERSION, GROUPING_VERSION

    now = observed_at or _utc_now()
    family_id = None
    evidence_ids: list[int] = []
    try:
        with _connect() as connection:
            connection.execute(
                """INSERT INTO product_eligibility
                   (product_id, content_type, eligibility_status, eligibility_reason,
                    eligibility_version, concrete_product_status,
                    concrete_product_reason, concrete_product_version, evaluated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(product_id) DO UPDATE SET
                    content_type=excluded.content_type,
                    eligibility_status=excluded.eligibility_status,
                    eligibility_reason=excluded.eligibility_reason,
                    eligibility_version=excluded.eligibility_version,
                    concrete_product_status=excluded.concrete_product_status,
                    concrete_product_reason=excluded.concrete_product_reason,
                    concrete_product_version=excluded.concrete_product_version,
                    evaluated_at=excluded.evaluated_at""",
                (product_id, eligibility.content_type, eligibility.eligibility_status,
                 eligibility.reason, eligibility.version, concrete.status,
                 concrete.reason, concrete.version, now),
            )
            connection.execute(
                """INSERT INTO product_identities
                   (product_id, source_title, normalized_product_name,
                    normalized_product_name_zh, normalization_method,
                    normalization_confidence, normalization_version, normalized_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(product_id) DO UPDATE SET
                    source_title=excluded.source_title,
                    normalized_product_name=excluded.normalized_product_name,
                    normalized_product_name_zh=COALESCE(excluded.normalized_product_name_zh,
                                                        product_identities.normalized_product_name_zh),
                    normalization_method=excluded.normalization_method,
                    normalization_confidence=excluded.normalization_confidence,
                    normalization_version=excluded.normalization_version,
                    normalized_at=excluded.normalized_at""",
                (product_id, identity.source_title, identity.normalized_product_name,
                 identity.normalized_product_name_zh, identity.method,
                 identity.confidence, identity.version, now),
            )
            if (family is None or eligibility.eligibility_status != "ELIGIBLE"
                    or concrete.status != "CONCRETE"):
                connection.execute(
                    """DELETE FROM product_family_members
                       WHERE product_id=? AND manual_override=?""",
                    (product_id, False),
                )
            if (family is not None and eligibility.eligibility_status == "ELIGIBLE"
                    and concrete.status == "CONCRETE"):
                connection.execute(
                    """INSERT INTO product_families
                       (family_key, canonical_name, canonical_name_zh, primary_category,
                        product_type, first_seen_at, last_seen_at, status,
                        grouping_version, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
                       ON CONFLICT(family_key) DO UPDATE SET
                        last_seen_at=excluded.last_seen_at,
                        status='ACTIVE',
                        canonical_name_zh=COALESCE(product_families.canonical_name_zh,
                                                   excluded.canonical_name_zh),
                        updated_at=excluded.updated_at""",
                    (family.family_key, family.canonical_name,
                     identity.normalized_product_name_zh, product.category,
                     family.product_type, now, now, GROUPING_VERSION, now, now),
                )
                family_row = connection.execute(
                    "SELECT id FROM product_families WHERE family_key = ?", (family.family_key,)
                ).fetchone()
                family_id = family_row["id"]
                connection.execute(
                    """INSERT INTO product_family_members
                       (family_id, product_id, match_method, match_score,
                        reviewed, manual_override, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(product_id) DO UPDATE SET
                        family_id=CASE WHEN product_family_members.manual_override THEN
                            product_family_members.family_id ELSE excluded.family_id END,
                        match_method=CASE WHEN product_family_members.manual_override THEN
                            product_family_members.match_method ELSE excluded.match_method END,
                        match_score=CASE WHEN product_family_members.manual_override THEN
                            product_family_members.match_score ELSE excluded.match_score END""",
                    (family_id, product_id, family.match_method, family.match_score,
                     False, False, now),
                )
            for fact in evidence_facts:
                scope = pipeline_run_id or "historical"
                evidence_key = f"{scope}:{product_id}:{fact.metric_name}"
                connection.execute(
                    """INSERT INTO source_evidence_snapshots
                       (product_id, family_id, pipeline_run_id, source_platform,
                        observed_at, evidence_type, metric_name, numeric_value,
                        text_value, raw_reference, evidence_version, evidence_key, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(evidence_key) DO UPDATE SET
                        family_id=excluded.family_id,
                        observed_at=excluded.observed_at,
                        numeric_value=excluded.numeric_value,
                        text_value=excluded.text_value,
                        raw_reference=excluded.raw_reference,
                        evidence_version=excluded.evidence_version""",
                    (product_id, family_id, pipeline_run_id, product.source_platform,
                     now, fact.evidence_type, fact.metric_name, fact.numeric_value,
                     fact.text_value, json.dumps({"raw_data_key": fact.metric_name}),
                     EVIDENCE_VERSION, evidence_key, now),
                )
                evidence_row = connection.execute(
                    "SELECT id FROM source_evidence_snapshots WHERE evidence_key = ?",
                    (evidence_key,),
                ).fetchone()
                evidence_ids.append(evidence_row["id"])
            if pipeline_run_id:
                connection.execute(
                    """INSERT INTO product_observations
                       (pipeline_run_id, product_id, observed_at, source_platform,
                        was_new, was_updated, evidence_snapshot_id, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(pipeline_run_id, product_id) DO UPDATE SET
                        observed_at=excluded.observed_at,
                        was_new=product_observations.was_new OR excluded.was_new,
                        was_updated=product_observations.was_updated OR excluded.was_updated,
                        evidence_snapshot_id=COALESCE(excluded.evidence_snapshot_id,
                                                      product_observations.evidence_snapshot_id)""",
                    (pipeline_run_id, product_id, now, product.source_platform,
                     bool(was_new), bool(was_updated), evidence_ids[0] if evidence_ids else None, now),
                )
        return {"product_id": product_id, "family_id": family_id,
                "evidence_records": len(evidence_ids), "observed": bool(pipeline_run_id)}
    except Exception:
        return {"product_id": product_id, "family_id": None,
                "evidence_records": 0, "observed": False}


def get_latest_completed_run() -> dict | None:
    """Return the latest completed/partial run, independent of calendar date."""
    try:
        with _connect() as connection:
            row = connection.execute(
                """SELECT * FROM pipeline_runs
                   WHERE status IN ('COMPLETED', 'PARTIAL') AND finished_at IS NOT NULL
                   ORDER BY finished_at DESC LIMIT 1"""
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def get_recent_completed_run_ids(cutoff_timestamp: str) -> list[str]:
    """Return completed/partial run IDs with observations inside a real time window."""
    try:
        with _connect() as connection:
            rows = connection.execute(
                """SELECT DISTINCT r.run_id, r.finished_at
                   FROM pipeline_runs r
                   JOIN product_observations o ON o.pipeline_run_id=r.run_id
                   WHERE r.status IN ('COMPLETED','PARTIAL')
                     AND r.finished_at IS NOT NULL AND o.observed_at>=?
                   ORDER BY r.finished_at DESC, r.run_id DESC""",
                (cutoff_timestamp,),
            ).fetchall()
        return [str(row["run_id"]) for row in rows]
    except Exception:
        return []


def get_source_failures_between(start_timestamp: str, end_timestamp: str) -> list[dict]:
    """Return recorded source failures overlapping the strict composition window."""
    try:
        with _connect() as connection:
            rows = connection.execute(
                """SELECT s.source_platform,s.error,r.run_id,r.started_at
                   FROM pipeline_source_runs s JOIN pipeline_runs r ON r.run_id=s.run_id
                   WHERE s.failed=? AND r.started_at>=? AND r.started_at<?
                   ORDER BY r.started_at,s.source_platform""",
                (True, start_timestamp, end_timestamp),
            ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []


def get_pipeline_source_failure_count(run_id: str) -> int:
    try:
        with _connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM pipeline_source_runs WHERE run_id=? AND failed=?",
                (run_id, True),
            ).fetchone()
        return int(row["count"] if row else 0)
    except Exception:
        return 0


def get_recent_daily_discovery(cutoff_timestamp: str) -> list[dict]:
    """Load the rolling eligible evidence pool with three bounded batch queries."""
    try:
        with _connect() as connection:
            families = connection.execute(
                """SELECT f.id AS family_id, f.canonical_name, f.canonical_name_zh,
                          f.primary_category, f.product_type, f.first_seen_at, f.last_seen_at,
                          MAX(o.observed_at) AS latest_observed_at
                   FROM product_observations o
                   JOIN products p ON p.id=o.product_id
                   JOIN product_eligibility e ON e.product_id=p.id
                   JOIN product_family_members fm ON fm.product_id=p.id
                   JOIN product_families f ON f.id=fm.family_id
                   WHERE o.observed_at>=? AND e.eligibility_status='ELIGIBLE'
                     AND e.concrete_product_status='CONCRETE' AND f.status='ACTIVE'
                   GROUP BY f.id,f.canonical_name,f.canonical_name_zh,f.primary_category,
                            f.product_type,f.first_seen_at,f.last_seen_at""",
                (cutoff_timestamp,),
            ).fetchall()
            records = connection.execute(
                """SELECT fm.family_id,p.source_platform,p.url,p.id AS product_id,
                          p.title AS source_title,p.category,p.description,p.raw_data,
                          MAX(o.observed_at) AS observation_timestamp
                   FROM product_observations o JOIN products p ON p.id=o.product_id
                   JOIN product_eligibility e ON e.product_id=p.id
                   JOIN product_family_members fm ON fm.product_id=p.id
                   JOIN product_families f ON f.id=fm.family_id
                   WHERE o.observed_at>=? AND e.eligibility_status='ELIGIBLE'
                     AND e.concrete_product_status='CONCRETE' AND f.status='ACTIVE'
                   GROUP BY fm.family_id,p.source_platform,p.url,p.id,p.title,p.category,p.description,p.raw_data
                   ORDER BY fm.family_id,p.source_platform,p.id""",
                (cutoff_timestamp,),
            ).fetchall()
            evidence = connection.execute(
                """SELECT s.family_id,s.source_platform,s.metric_name,s.numeric_value,s.text_value
                   FROM source_evidence_snapshots s
                   JOIN product_families f ON f.id=s.family_id
                   WHERE s.observed_at>=? AND f.status='ACTIVE'
                   ORDER BY s.family_id,s.source_platform,s.metric_name""",
                (cutoff_timestamp,),
            ).fetchall()
        records_by_family: dict[int, list[dict]] = {}
        for row in records:
            value = dict(row); value["raw_data"] = _decode_json(value.get("raw_data"), {})
            records_by_family.setdefault(int(value.pop("family_id")), []).append(value)
        evidence_by_family: dict[int, list[dict]] = {}
        for row in evidence:
            value = dict(row)
            evidence_by_family.setdefault(int(value.pop("family_id")), []).append(value)
        from evidence_foundation import EvidenceFact, assess_evidence_strength
        output = []
        for row in families:
            item = dict(row); family_id = int(item["family_id"])
            source_records = records_by_family.get(family_id, [])
            item["source_records"] = source_records
            item["source_platforms"] = sorted({r["source_platform"] for r in source_records})
            descriptions = [" ".join(str(r.get("description") or "").split()) for r in source_records if str(r.get("description") or "").strip()]
            item["factual_description"] = min(descriptions, key=len)[:300] if descriptions else ""
            evidence_rows = evidence_by_family.get(family_id, [])
            grouped: dict[str, list] = {}
            for fact in evidence_rows:
                grouped.setdefault(fact["source_platform"], []).append(EvidenceFact(fact["metric_name"], fact["numeric_value"], fact["text_value"]))
            assessments = [assess_evidence_strength(source, facts, independent_source_count=len(item["source_platforms"])) for source, facts in grouped.items()]
            order = {"WEAK": 0, "MODERATE": 1, "STRONG": 2}
            strongest = max(assessments, key=lambda value: order[value.strength], default=None)
            item["evidence_strength"] = strongest.strength if strongest else "WEAK"
            item["evidence_reasons"] = strongest.reasons if strongest else ["No source-native market metrics are currently available."]
            item["evidence_facts"] = evidence_rows
            output.append(item)
        return output
    except Exception:
        return []


def get_observations_for_run(run_id: str) -> list[dict]:
    try:
        with _connect() as connection:
            rows = connection.execute(
                """SELECT o.*, p.url, p.title, p.description, p.category, p.raw_data
                   FROM product_observations o JOIN products p ON p.id=o.product_id
                   WHERE o.pipeline_run_id=? ORDER BY o.id""", (run_id,)
            ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []


def get_products_for_run(run_id: str) -> list[dict]:
    return get_observations_for_run(run_id)


def get_supported_product_records_for_run(run_id: str) -> list[dict]:
    """Infer only observations supported by a run interval and source ledger.

    This is intended for the bounded first shadow backfill. It does not infer
    membership from ``first_seen_at`` and ignores failed/empty sources.
    """
    try:
        with _connect() as connection:
            run = connection.execute(
                "SELECT started_at, finished_at FROM pipeline_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if not run or not run["finished_at"]:
                return []
            sources = connection.execute(
                """SELECT source_platform FROM pipeline_source_runs
                   WHERE run_id=? AND failed=? AND fetched>0""", (run_id, False),
            ).fetchall()
            names = [row["source_platform"] for row in sources]
            if not names:
                return []
            placeholders = ",".join("?" for _ in names)
            rows = connection.execute(
                f"""SELECT * FROM products
                    WHERE source_platform IN ({placeholders})
                      AND last_seen_at>=? AND last_seen_at<=?
                    ORDER BY id""",
                tuple(names) + (run["started_at"], run["finished_at"]),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["raw_data"] = _decode_json(item.get("raw_data"), {})
            output.append(item)
        return output
    except Exception:
        return []


def get_daily_discovery(run_id: str | None = None) -> list[dict]:
    """Return every eligible family observed in a run; never Top-N or AI-gated."""
    selected = {"run_id": run_id} if run_id else get_latest_completed_run()
    if not selected:
        return []
    run_id = selected["run_id"]
    try:
        with _connect() as connection:
            rows = connection.execute(
                """SELECT f.id AS family_id, f.canonical_name, f.canonical_name_zh,
                          f.primary_category, f.product_type, f.first_seen_at,
                          f.last_seen_at, MAX(o.observed_at) AS latest_observed_at,
                          COUNT(DISTINCT p.source_platform) AS source_count
                   FROM product_observations o
                   JOIN products p ON p.id=o.product_id
                   JOIN product_eligibility e ON e.product_id=p.id
                   JOIN product_family_members fm ON fm.product_id=p.id
                   JOIN product_families f ON f.id=fm.family_id
                   WHERE o.pipeline_run_id=? AND e.eligibility_status='ELIGIBLE'
                     AND e.concrete_product_status='CONCRETE' AND f.status='ACTIVE'
                   GROUP BY f.id, f.canonical_name, f.canonical_name_zh,
                            f.primary_category, f.product_type,
                            f.first_seen_at, f.last_seen_at
                   ORDER BY f.canonical_name""", (run_id,)
            ).fetchall()
            output = []
            for row in rows:
                item = dict(row)
                sources = connection.execute(
                    """SELECT DISTINCT p.source_platform, p.url, p.id AS product_id,
                                      p.title AS source_title, p.category, p.description, p.raw_data
                       FROM product_observations o JOIN products p ON p.id=o.product_id
                       JOIN product_family_members fm ON fm.product_id=p.id
                       WHERE o.pipeline_run_id=? AND fm.family_id=?
                       ORDER BY p.source_platform, p.id""", (run_id, item["family_id"]),
                ).fetchall()
                item["source_records"] = [dict(source) for source in sources]
                for source in item["source_records"]:
                    source["raw_data"] = _decode_json(source.get("raw_data"), {})
                item["source_platforms"] = sorted({source["source_platform"] for source in sources})
                descriptions = [
                    " ".join(str(source.get("description") or "").split())
                    for source in item["source_records"]
                    if str(source.get("description") or "").strip()
                ]
                item["factual_description"] = min(descriptions, key=len)[:300] if descriptions else ""
                evidence_rows = connection.execute(
                    """SELECT source_platform, metric_name, numeric_value, text_value
                       FROM source_evidence_snapshots
                       WHERE family_id=? AND pipeline_run_id=?
                       ORDER BY source_platform, metric_name""",
                    (item["family_id"], run_id),
                ).fetchall()
                from evidence_foundation import EvidenceFact, assess_evidence_strength
                grouped: dict[str, list] = {}
                for evidence in evidence_rows:
                    grouped.setdefault(evidence["source_platform"], []).append(EvidenceFact(
                        evidence["metric_name"], evidence["numeric_value"], evidence["text_value"],
                    ))
                assessments = [
                    assess_evidence_strength(
                        source, facts, independent_source_count=len(item["source_platforms"]),
                    )
                    for source, facts in grouped.items()
                ]
                order = {"WEAK": 0, "MODERATE": 1, "STRONG": 2}
                strongest = max(assessments, key=lambda value: order[value.strength], default=None)
                item["evidence_strength"] = strongest.strength if strongest else "WEAK"
                item["evidence_reasons"] = strongest.reasons if strongest else [
                    "No source-native market metrics are currently available."
                ]
                item["evidence_facts"] = [dict(value) for value in evidence_rows]
                item["latest_run_id"] = run_id
                output.append(item)
        return output
    except Exception:
        return []


def persist_daily_discovery_snapshot(
    pipeline_run_id: str, items: list[dict], *, discovery_date: str, metadata: dict | None = None
) -> str | None:
    """Atomically persist the authoritative ordered snapshot for one pipeline run."""
    daily_run_id = f"daily:{pipeline_run_id}"
    now = _utc_now()
    try:
        with _connect() as connection:
            connection.execute(
                """INSERT INTO daily_discovery_runs
                   (run_id,pipeline_run_id,discovery_date,generated_at,status,item_count,metadata_json)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(pipeline_run_id) DO UPDATE SET
                    discovery_date=excluded.discovery_date, generated_at=excluded.generated_at,
                    status=excluded.status, item_count=excluded.item_count,
                    metadata_json=excluded.metadata_json""",
                (daily_run_id, pipeline_run_id, discovery_date, now, "COMPLETED", len(items),
                 json.dumps(metadata or {}, ensure_ascii=False)),
            )
            connection.execute("DELETE FROM daily_discovery_items WHERE daily_run_id=?", (daily_run_id,))
            for position, item in enumerate(items, 1):
                snapshot = dict(item)
                snapshot["display_order"] = position
                connection.execute(
                    """INSERT INTO daily_discovery_items
                       (daily_run_id,family_id,display_order,canonical_name,canonical_name_zh,
                        product_type,evidence_strength,snapshot_json,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (daily_run_id, item["family_id"], position, item["canonical_name"],
                     item.get("canonical_name_zh"), item.get("product_type", "unknown"),
                     item.get("evidence_strength", "WEAK"),
                     json.dumps(snapshot, ensure_ascii=False, default=str), now),
                )
        return daily_run_id
    except (KeyError, TypeError, sqlite3.Error):
        return None


def get_persisted_daily_discovery(
    *, daily_run_id: str | None = None, pipeline_run_id: str | None = None
) -> dict | None:
    """Load one immutable daily snapshot, latest completed when no identity is supplied."""
    try:
        with _connect() as connection:
            if daily_run_id:
                row = connection.execute("SELECT * FROM daily_discovery_runs WHERE run_id=?", (daily_run_id,)).fetchone()
            elif pipeline_run_id:
                row = connection.execute("SELECT * FROM daily_discovery_runs WHERE pipeline_run_id=?", (pipeline_run_id,)).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM daily_discovery_runs WHERE status='COMPLETED' ORDER BY generated_at DESC, run_id DESC LIMIT 1"
                ).fetchone()
            if not row:
                return None
            result = dict(row)
            result["metadata"] = _decode_json(result.pop("metadata_json", "{}"), {})
            item_rows = connection.execute(
                "SELECT snapshot_json FROM daily_discovery_items WHERE daily_run_id=? ORDER BY display_order", (result["run_id"],)
            ).fetchall()
            result["items"] = [_decode_json(value["snapshot_json"], {}) for value in item_rows]
            return result
    except sqlite3.Error:
        return None


def update_daily_discovery_item_language(
    daily_run_id: str, family_id: int, canonical_name_zh: str, factual_description_zh: str
) -> bool:
    """Update presentation language only; membership and display order are immutable."""
    try:
        with _connect() as connection:
            row = connection.execute(
                "SELECT snapshot_json FROM daily_discovery_items WHERE daily_run_id=? AND family_id=?",
                (daily_run_id, family_id),
            ).fetchone()
            if not row:
                return False
            snapshot = _decode_json(row["snapshot_json"], {})
            snapshot["canonical_name_zh"] = canonical_name_zh
            snapshot["factual_description_zh"] = factual_description_zh
            cursor = connection.execute(
                """UPDATE daily_discovery_items
                   SET canonical_name_zh=?, snapshot_json=?
                   WHERE daily_run_id=? AND family_id=?""",
                (canonical_name_zh, json.dumps(snapshot, ensure_ascii=False, default=str), daily_run_id, family_id),
            )
        return cursor.rowcount == 1
    except (TypeError, sqlite3.Error):
        return False


def persist_daily_picks_snapshot(daily_discovery_run_id: str, items: list[dict], target_count: int = 20) -> str:
    """Persist one deterministic Picks projection without changing Discovery membership."""
    run_id = f"picks:{daily_discovery_run_id}"
    now = _utc_now()
    try:
        with _connect() as connection:
            for item in items:
                connection.execute(
                    """INSERT INTO product_directions
                       (direction_id,direction_key,name_en,name_zh,description_zh,direction_type,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(direction_id) DO UPDATE SET
                       direction_key=excluded.direction_key,name_en=excluded.name_en,name_zh=excluded.name_zh,
                       description_zh=excluded.description_zh,direction_type=excluded.direction_type,updated_at=excluded.updated_at""",
                    (item["direction_id"], item["direction_key"], item["name_en"], item["name_zh"],
                     item["description_zh"], item.get("product_type", ""), now, now),
                )
                for family_id in item.get("member_family_ids", [item["family_id"]]):
                    connection.execute(
                        """INSERT INTO product_direction_members
                           (direction_id,family_id,match_reason,match_confidence,created_at)
                           VALUES (?,?,?,?,?) ON CONFLICT(direction_id,family_id) DO UPDATE SET
                           match_reason=excluded.match_reason,match_confidence=excluded.match_confidence""",
                        (item["direction_id"], int(family_id), item.get("aggregation_reason", ""),
                         item.get("aggregation_confidence", "MEDIUM"), now),
                    )
            connection.execute(
                """INSERT INTO daily_picks_runs
                   (run_id,daily_discovery_run_id,generated_at,target_count,item_count,status,metadata_json)
                   VALUES (?,?,?,?,?,'COMPLETED',?)
                   ON CONFLICT(daily_discovery_run_id) DO UPDATE SET
                    generated_at=excluded.generated_at,target_count=excluded.target_count,
                    item_count=excluded.item_count,status='COMPLETED',metadata_json=excluded.metadata_json""",
                (run_id, daily_discovery_run_id, now, target_count, len(items),
                 json.dumps({"membership": "deterministic-diverse-daily-picks", "ai_gate": False})),
            )
            connection.execute("DELETE FROM daily_picks_items WHERE picks_run_id=?", (run_id,))
            for order, item in enumerate(items, 1):
                connection.execute(
                    """INSERT INTO daily_picks_items
                       (picks_run_id,family_id,pick_order,snapshot_json,created_at,direction_id)
                       VALUES (?,?,?,?,?,?)""",
                    (run_id, int(item["family_id"]), order,
                     json.dumps(item, ensure_ascii=False, default=str), now, item.get("direction_id")),
                )
        return run_id
    except Exception:
        return ""


def get_persisted_daily_picks(*, run_id: str | None = None, daily_discovery_run_id: str | None = None) -> dict | None:
    try:
        with _connect() as connection:
            if run_id:
                row = connection.execute("SELECT * FROM daily_picks_runs WHERE run_id=?", (run_id,)).fetchone()
            elif daily_discovery_run_id:
                row = connection.execute("SELECT * FROM daily_picks_runs WHERE daily_discovery_run_id=?", (daily_discovery_run_id,)).fetchone()
            else:
                row = connection.execute("SELECT * FROM daily_picks_runs WHERE status='COMPLETED' ORDER BY generated_at DESC LIMIT 1").fetchone()
            if not row:
                return None
            result = dict(row)
            snapshots = connection.execute(
                "SELECT snapshot_json FROM daily_picks_items WHERE picks_run_id=? ORDER BY pick_order", (result["run_id"],)
            ).fetchall()
        result["items"] = [_decode_json(value["snapshot_json"], {}) for value in snapshots]
        result["item_count"] = len(result["items"])
        return result
    except Exception:
        return None


def save_user_voice_items(items: list[dict]) -> tuple[int, int]:
    saved = duplicates = 0
    try:
        with _connect() as connection:
            for item in items:
                cursor = connection.execute(
                    """INSERT INTO user_voice_items
                       (product_family_id,product_id,source,source_item_id,author,original_text,
                        original_language,source_url,published_at,engagement_json,retrieved_at,voice_type,identity_key,
                        product_direction_id,translated_text_zh,score_or_likes,source_post_id,source_comment_id,
                        parent_feedback_id,retrieval_method,traceable,is_platform_ai_summary,content_hash,metadata_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(identity_key) DO NOTHING""",
                    (item["product_family_id"], item.get("product_id"), item["source"], item.get("source_item_id"),
                     item.get("author"), item["original_text"], item.get("original_language", "unknown"),
                     item["source_url"], item.get("published_at"), json.dumps(item.get("engagement", {})),
                     item["retrieved_at"], item.get("voice_type", "OTHER_DISCUSSION"), item["identity_key"],
                     item.get("product_direction_id"), item.get("translated_text_zh"), item.get("score_or_likes"),
                     item.get("source_post_id"), item.get("source_comment_id"), item.get("parent_feedback_id"),
                     item.get("retrieval_method"), int(bool(item.get("traceable", True))),
                     int(bool(item.get("is_platform_ai_summary", False))), item.get("content_hash"),
                     json.dumps(item.get("metadata", {}), ensure_ascii=False, default=str)),
                )
                if cursor.rowcount == 1:
                    saved += 1
                else:
                    duplicates += 1
        return saved, duplicates
    except Exception:
        return 0, 0


def get_user_voice_items(family_id: int) -> list[dict]:
    try:
        with _connect() as connection:
            rows = connection.execute(
                "SELECT * FROM user_voice_items WHERE product_family_id=? ORDER BY retrieved_at,id", (family_id,)
            ).fetchall()
        return [{**dict(row), "engagement": _decode_json(row["engagement_json"], {})} for row in rows]
    except Exception:
        return []


def get_user_voice_items_map(family_ids: list[int]) -> dict[int, list[dict]]:
    """Load persisted voice for a composition pool in one query."""
    if not family_ids:
        return {}
    try:
        with _connect() as connection:
            if DATABASE_SETTINGS.backend == "postgresql":
                rows = connection.execute(
                    "SELECT * FROM user_voice_items WHERE product_family_id = ANY(?) ORDER BY product_family_id,retrieved_at,id",
                    (family_ids,),
                ).fetchall()
            else:
                placeholders = ",".join("?" for _ in family_ids)
                rows = connection.execute(
                    f"SELECT * FROM user_voice_items WHERE product_family_id IN ({placeholders}) ORDER BY product_family_id,retrieved_at,id",
                    tuple(family_ids),
                ).fetchall()
        output: dict[int, list[dict]] = {}
        for row in rows:
            value = dict(row); value["engagement"] = _decode_json(value.get("engagement_json"), {})
            output.setdefault(int(value["product_family_id"]), []).append(value)
        return output
    except Exception:
        return {}


def is_notification_delivered(delivery_key: str) -> bool:
    try:
        with _connect() as connection:
            row = connection.execute(
                "SELECT status FROM notification_deliveries WHERE delivery_key=?", (delivery_key,)
            ).fetchone()
        return bool(row and row["status"] == "DELIVERED")
    except Exception:
        return False


def get_notification_delivery_status(delivery_key: str) -> str | None:
    """Return safe delivery state without exposing recipient or credentials."""
    try:
        with _connect() as connection:
            row = connection.execute(
                "SELECT status FROM notification_deliveries WHERE delivery_key=?", (delivery_key,)
            ).fetchone()
        return str(row["status"]) if row else None
    except Exception:
        return None


def record_notification_delivery(
    delivery_key: str, daily_run_id: str, recipient_hash: str,
    chunk_count: int, delivered_chunks: int,
) -> None:
    """Persist only a recipient hash; never persist UID or token."""
    now = _utc_now()
    status = "DELIVERED" if chunk_count and delivered_chunks == chunk_count else "PARTIAL"
    with _connect() as connection:
        connection.execute(
            """INSERT INTO notification_deliveries
               (delivery_key,daily_run_id,channel,recipient_hash,status,chunk_count,delivered_chunks,created_at,updated_at)
               VALUES (?,?,'wxpusher',?,?,?,?,?,?) ON CONFLICT(delivery_key) DO UPDATE SET
               status=excluded.status,chunk_count=excluded.chunk_count,
               delivered_chunks=excluded.delivered_chunks,updated_at=excluded.updated_at""",
            (delivery_key, daily_run_id, recipient_hash, status, chunk_count, delivered_chunks, now, now),
        )


def get_family_enrichment(
    family_id: int, identity_fingerprint: str, enrichment_version: str | None = None
) -> dict | None:
    try:
        with _connect() as connection:
            if enrichment_version:
                row = connection.execute(
                    """SELECT * FROM product_family_enrichments
                       WHERE family_id=? AND identity_fingerprint=?
                         AND enrichment_version=? AND status='COMPLETED'""",
                    (family_id, identity_fingerprint, enrichment_version),
                ).fetchone()
            else:
                row = connection.execute(
                    """SELECT * FROM product_family_enrichments
                       WHERE family_id=? AND identity_fingerprint=? AND status='COMPLETED'""",
                    (family_id, identity_fingerprint),
                ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        return None


def save_family_enrichment(
    family_id: int, identity_fingerprint: str, canonical_name_en: str,
    canonical_name_zh: str, factual_description_zh: str,
    *, enrichment_version: str,
) -> bool:
    try:
        with _connect() as connection:
            connection.execute(
                """INSERT INTO product_family_enrichments
                   (family_id,identity_fingerprint,canonical_name_en,canonical_name_zh,
                    factual_description_zh,enrichment_version,status,error_type,generated_at)
                   VALUES (?,?,?,?,?,?, 'COMPLETED','',?)
                   ON CONFLICT(family_id) DO UPDATE SET
                    identity_fingerprint=excluded.identity_fingerprint,
                    canonical_name_en=excluded.canonical_name_en,
                    canonical_name_zh=excluded.canonical_name_zh,
                    factual_description_zh=excluded.factual_description_zh,
                    enrichment_version=excluded.enrichment_version,
                    status='COMPLETED', error_type='', generated_at=excluded.generated_at""",
                (family_id, identity_fingerprint, canonical_name_en, canonical_name_zh,
                 factual_description_zh, enrichment_version, _utc_now()),
            )
        return True
    except sqlite3.Error:
        return False


def save_family_feedback(family_id: int, feedback_type: str, reason: str = "", note: str = "") -> bool:
    payload = json.dumps({"reason": reason, "note": note}, ensure_ascii=False)
    return save_user_feedback("family", str(family_id), feedback_type, payload)


def get_family_feedback_map() -> dict[int, dict]:
    try:
        with _connect() as connection:
            rows = connection.execute(
                "SELECT entity_id,feedback_type,note,updated_at FROM user_product_feedback WHERE entity_type='family'"
            ).fetchall()
        return {int(row["entity_id"]): {**dict(row), "details": _decode_json(row["note"], {})} for row in rows}
    except (ValueError, sqlite3.Error):
        return {}


def get_shadow_counts() -> dict[str, int]:
    tables = (
        "products", "product_eligibility", "product_identities", "product_families",
        "product_family_members", "product_observations", "source_evidence_snapshots",
        "user_product_feedback", "re_evaluation_requests",
    )
    counts = {}
    try:
        with _connect() as connection:
            for table in tables:
                counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            counts["active_product_families"] = connection.execute(
                "SELECT COUNT(*) FROM product_families WHERE status='ACTIVE'"
            ).fetchone()[0]
        return counts
    except Exception:
        return counts


def prune_empty_shadow_families() -> int:
    """Deactivate orphaned shadow families while preserving grouping history."""
    try:
        with _connect() as connection:
            cursor = connection.execute(
                """UPDATE product_families SET status='INACTIVE', updated_at=?
                   WHERE status='ACTIVE' AND NOT EXISTS (
                     SELECT 1 FROM product_family_members fm
                     WHERE fm.family_id=product_families.id
                   )""", (_utc_now(),)
            )
        return max(0, cursor.rowcount)
    except Exception:
        return 0


def refresh_shadow_family_canonical_names() -> int:
    """Choose concise canonical names from the best deterministic identities."""
    updated = 0
    try:
        with _connect() as connection:
            families = connection.execute("SELECT id FROM product_families").fetchall()
            now = _utc_now()
            for family in families:
                manually_reviewed = connection.execute(
                    """SELECT 1 FROM product_family_members
                       WHERE family_id=? AND manual_override=? LIMIT 1""",
                    (family["id"], True),
                ).fetchone()
                if manually_reviewed:
                    continue
                choices = connection.execute(
                    """SELECT i.normalized_product_name, i.normalized_product_name_zh,
                              i.normalization_confidence
                       FROM product_family_members fm
                       JOIN product_identities i ON i.product_id=fm.product_id
                       JOIN product_eligibility e ON e.product_id=fm.product_id
                       WHERE fm.family_id=? AND e.eligibility_status='ELIGIBLE'
                         AND e.concrete_product_status='CONCRETE'
                         AND i.normalized_product_name IS NOT NULL
                       ORDER BY CASE i.normalization_confidence
                                  WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END,
                                LENGTH(i.normalized_product_name), i.product_id
                       LIMIT 1""", (family["id"],),
                ).fetchone()
                if not choices:
                    continue
                cursor = connection.execute(
                    """UPDATE product_families
                       SET canonical_name=?,
                           canonical_name_zh=COALESCE(?, canonical_name_zh),
                           updated_at=? WHERE id=?""",
                    (choices["normalized_product_name"],
                     choices["normalized_product_name_zh"], now, family["id"]),
                )
                updated += int(cursor.rowcount == 1)
        return updated
    except Exception:
        return 0


def get_family_feedback(family_id: int) -> list[dict]:
    """Project existing Product feedback onto a family without migrating it."""
    try:
        with _connect() as connection:
            rows = connection.execute(
                """SELECT uf.*, fm.family_id, fm.product_id
                   FROM product_family_members fm
                   JOIN user_product_feedback uf
                     ON uf.entity_type='product' AND uf.entity_id=CAST(fm.product_id AS TEXT)
                   WHERE fm.family_id=? ORDER BY uf.updated_at DESC, uf.id DESC""",
                (family_id,),
            ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []


def save_candidates(
    candidates: list[MicroInnovationCandidate],
) -> tuple[int, int]:
    """Insert candidates without duplicating candidate IDs or source URLs."""
    if not init_db():
        return 0, 0
    if DATABASE_SETTINGS.backend == "postgresql":
        return _save_candidates_postgres_batch(candidates)
    saved_count = 0
    duplicate_count = 0
    try:
        with _connect() as connection:
            for candidate in candidates:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO micro_innovation_candidates (
                        candidate_id, candidate_type, source_platform, source_url,
                        title, summary, candidate_score, feasibility_score,
                        demand_score, market_validation_score,
                        micro_innovation_score, reason, signals, raw_reference_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate.candidate_id,
                        candidate.candidate_type,
                        candidate.source_platform,
                        candidate.source_url,
                        candidate.title,
                        candidate.summary,
                        candidate.candidate_score,
                        candidate.feasibility_score,
                        candidate.demand_score,
                        candidate.market_validation_score,
                        candidate.micro_innovation_score,
                        candidate.reason,
                        json.dumps(candidate.signals, ensure_ascii=False),
                        candidate.raw_reference_id,
                    ),
                )
                if cursor.rowcount == 1:
                    saved_count += 1
                else:
                    duplicate_count += 1
        return saved_count, duplicate_count
    except (AttributeError, TypeError, ValueError, sqlite3.Error):
        return 0, 0


def _save_candidates_postgres_batch(
    candidates: list[MicroInnovationCandidate],
) -> tuple[int, int]:
    """Insert a candidate set with one PostgreSQL round trip."""
    if not candidates:
        return 0, 0
    columns = (
        "candidate_id", "candidate_type", "source_platform", "source_url",
        "title", "summary", "candidate_score", "feasibility_score",
        "demand_score", "market_validation_score", "micro_innovation_score",
        "reason", "signals", "raw_reference_id",
    )
    group = "(" + ",".join(["%s"] * len(columns)) + ")"
    values = []
    for candidate in candidates:
        values.extend((
            candidate.candidate_id, candidate.candidate_type,
            candidate.source_platform, candidate.source_url, candidate.title,
            candidate.summary, candidate.candidate_score,
            candidate.feasibility_score, candidate.demand_score,
            candidate.market_validation_score,
            candidate.micro_innovation_score, candidate.reason,
            json.dumps(candidate.signals, ensure_ascii=False),
            candidate.raw_reference_id,
        ))
    try:
        with _connect() as connection:
            cursor = connection.execute(
                f"""INSERT INTO micro_innovation_candidates ({','.join(columns)})
                    VALUES {','.join([group] * len(candidates))}
                    ON CONFLICT DO NOTHING""",
                tuple(values),
            )
        saved_count = max(cursor.rowcount, 0)
        return saved_count, len(candidates) - saved_count
    except Exception:
        return 0, 0


def get_all_candidates() -> list[MicroInnovationCandidate]:
    """Return candidates ordered by descending candidate score."""
    try:
        if not init_db():
            return []
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT candidate_id, candidate_type, source_platform, source_url,
                       title, summary, candidate_score, feasibility_score,
                       demand_score, market_validation_score,
                       micro_innovation_score, reason, signals, raw_reference_id
                FROM micro_innovation_candidates
                ORDER BY candidate_score DESC, id
                """
            ).fetchall()
        return [
            MicroInnovationCandidate(
                candidate_id=row["candidate_id"],
                candidate_type=row["candidate_type"],
                source_platform=row["source_platform"],
                source_url=row["source_url"],
                title=row["title"],
                summary=row["summary"],
                candidate_score=row["candidate_score"],
                feasibility_score=row["feasibility_score"],
                demand_score=row["demand_score"],
                market_validation_score=row["market_validation_score"],
                micro_innovation_score=row["micro_innovation_score"],
                reason=row["reason"],
                signals=_decode_json(row["signals"], []),
                raw_reference_id=row["raw_reference_id"],
            )
            for row in rows
        ]
    except (json.JSONDecodeError, ValueError, sqlite3.Error):
        return []


def has_triage_result(candidate_id: str, provider: str, model: str) -> bool:
    try:
        if not init_db():
            return False
        with _connect() as connection:
            return connection.execute(
                """SELECT 1 FROM ai_triage_results
                   WHERE candidate_id = ? AND provider = ? AND model = ?""",
                (candidate_id, provider, model),
            ).fetchone() is not None
    except sqlite3.Error:
        return False


def get_triage_candidate_ids(provider: str, model: str) -> set[str]:
    """Load provider/model coverage in one query to avoid per-candidate checks."""
    try:
        if not init_db():
            return set()
        with _connect() as connection:
            rows = connection.execute(
                """SELECT candidate_id FROM ai_triage_results
                   WHERE provider = ? AND model = ?""",
                (provider, model),
            ).fetchall()
        return {row["candidate_id"] for row in rows}
    except sqlite3.Error:
        return set()


def save_triage_result(result: AITriageResult, *, force_reanalyze: bool = False) -> bool:
    """Insert one provider/model result, optionally updating that exact result."""
    try:
        if not init_db():
            return False
        with _connect() as connection:
            sql = """INSERT INTO ai_triage_results (
                    candidate_id, triage_status, triage_score, confidence,
                    primary_reason, opportunity_type, key_opportunity,
                    main_risks, needs_deep_analysis, provider, model,
                    display_title_zh, primary_reason_zh, key_opportunity_zh,
                    main_risks_zh, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            if force_reanalyze:
                sql += """ ON CONFLICT(candidate_id, provider, model) DO UPDATE SET
                    triage_status=excluded.triage_status,
                    triage_score=excluded.triage_score,
                    confidence=excluded.confidence,
                    primary_reason=excluded.primary_reason,
                    opportunity_type=excluded.opportunity_type,
                    key_opportunity=excluded.key_opportunity,
                    main_risks=excluded.main_risks,
                    needs_deep_analysis=excluded.needs_deep_analysis,
                    display_title_zh=excluded.display_title_zh,
                    primary_reason_zh=excluded.primary_reason_zh,
                    key_opportunity_zh=excluded.key_opportunity_zh,
                    main_risks_zh=excluded.main_risks_zh,
                    analyzed_at=excluded.analyzed_at"""
            else:
                sql += " ON CONFLICT(candidate_id, provider, model) DO NOTHING"
            cursor = connection.execute(
                sql, (result.candidate_id, result.triage_status, result.triage_score,
                 result.confidence, result.primary_reason, result.opportunity_type,
                 result.key_opportunity, json.dumps(result.main_risks, ensure_ascii=False),
                 bool(result.needs_deep_analysis), result.provider, result.model,
                 result.display_title_zh, result.primary_reason_zh,
                 result.key_opportunity_zh,
                 json.dumps(result.main_risks_zh, ensure_ascii=False),
                 result.analyzed_at),
            )
        return cursor.rowcount == 1
    except (TypeError, ValueError, sqlite3.Error):
        return False


def get_triage_result(candidate_id: str, provider: str | None = None, model: str | None = None) -> AITriageResult | None:
    try:
        if not init_db():
            return None
        with _connect() as connection:
            if provider is not None and model is not None:
                row = connection.execute(
                    """SELECT * FROM ai_triage_results
                       WHERE candidate_id = ? AND provider = ? AND model = ?""",
                    (candidate_id, provider, model),
                ).fetchone()
            else:
                row = connection.execute(
                    """SELECT * FROM ai_triage_results WHERE candidate_id = ?
                       ORDER BY analyzed_at DESC LIMIT 1""", (candidate_id,)
                ).fetchone()
        if row is None:
            return None
        return AITriageResult(
            candidate_id=row["candidate_id"], triage_status=row["triage_status"],
            triage_score=row["triage_score"], confidence=row["confidence"],
            primary_reason=row["primary_reason"], opportunity_type=row["opportunity_type"],
            key_opportunity=row["key_opportunity"], main_risks=_decode_json(row["main_risks"], []),
            needs_deep_analysis=bool(row["needs_deep_analysis"]), provider=row["provider"],
            model=row["model"], display_title_zh=row["display_title_zh"],
            primary_reason_zh=row["primary_reason_zh"],
            key_opportunity_zh=row["key_opportunity_zh"],
            main_risks_zh=_decode_json(row["main_risks_zh"], []),
            analyzed_at=_text_timestamp(row["analyzed_at"]),
        )
    except (json.JSONDecodeError, ValueError, sqlite3.Error):
        return None


def get_triage_results(candidate_id: str) -> list[AITriageResult]:
    """Return every provider/model result for one candidate."""
    try:
        if not init_db():
            return []
        with _connect() as connection:
            rows = connection.execute(
                """SELECT * FROM ai_triage_results WHERE candidate_id = ?
                   ORDER BY provider, model""", (candidate_id,)
            ).fetchall()
        return [_triage_row_to_result(row) for row in rows]
    except (json.JSONDecodeError, ValueError, sqlite3.Error):
        return []


def _triage_row_to_result(row: sqlite3.Row) -> AITriageResult:
    return AITriageResult(
        candidate_id=row["candidate_id"], triage_status=row["triage_status"],
        triage_score=row["triage_score"], confidence=row["confidence"],
        primary_reason=row["primary_reason"], opportunity_type=row["opportunity_type"],
        key_opportunity=row["key_opportunity"], main_risks=_decode_json(row["main_risks"], []),
        needs_deep_analysis=bool(row["needs_deep_analysis"]), provider=row["provider"],
        model=row["model"], display_title_zh=row["display_title_zh"],
        primary_reason_zh=row["primary_reason_zh"],
        key_opportunity_zh=row["key_opportunity_zh"],
        main_risks_zh=_decode_json(row["main_risks_zh"], []),
        analyzed_at=_text_timestamp(row["analyzed_at"]),
    )


def get_candidate_commodity() -> dict[str, tuple[str, int]]:
    """Return persisted Amazon commodity decisions keyed by candidate ID."""
    try:
        if not init_db():
            return {}
        with _connect() as connection:
            rows = connection.execute(
                """SELECT c.candidate_id, p.commodity_status, p.commodity_score
                   FROM micro_innovation_candidates c
                   JOIN products p ON p.url = c.source_url
                   WHERE c.candidate_type = 'consumer_trend'"""
            ).fetchall()
        return {row["candidate_id"]: (row["commodity_status"], row["commodity_score"]) for row in rows}
    except sqlite3.Error:
        return {}


def has_deep_analysis_result(
    candidate_id: str, provider: str, model: str, analysis_version: str
) -> bool:
    try:
        if not init_db():
            return False
        with _connect() as connection:
            return connection.execute(
                """SELECT 1 FROM deep_analysis_results
                   WHERE candidate_id = ? AND provider = ? AND model = ?
                     AND analysis_version = ?""",
                (candidate_id, provider, model, analysis_version),
            ).fetchone() is not None
    except sqlite3.Error:
        return False


def save_deep_analysis_result(
    result: DeepAnalysisResult, *, force_reanalyze: bool = False
) -> bool:
    try:
        if not init_db():
            return False
        with _connect() as connection:
            sql = """INSERT INTO deep_analysis_results (
                candidate_id, provider, model, analysis_version, deep_score,
                recommended_next_step, result_json, input_characters,
                input_tokens, output_tokens, total_tokens, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            if force_reanalyze:
                sql += """ ON CONFLICT(candidate_id, provider, model, analysis_version)
                    DO UPDATE SET deep_score=excluded.deep_score,
                    recommended_next_step=excluded.recommended_next_step,
                    result_json=excluded.result_json,
                    input_characters=excluded.input_characters,
                    input_tokens=excluded.input_tokens,
                    output_tokens=excluded.output_tokens,
                    total_tokens=excluded.total_tokens,
                    updated_at=excluded.updated_at"""
            else:
                sql += " ON CONFLICT(candidate_id, provider, model, analysis_version) DO NOTHING"
            cursor = connection.execute(sql, (
                result.candidate_id, result.provider, result.model,
                result.analysis_version, result.deep_score,
                result.recommended_next_step, result.model_dump_json(),
                result.input_characters, result.input_tokens, result.output_tokens,
                result.total_tokens, result.created_at, result.updated_at,
            ))
        return cursor.rowcount == 1
    except (TypeError, ValueError, sqlite3.Error):
        return False


def get_deep_analysis_result(
    candidate_id: str, provider: str, model: str, analysis_version: str
) -> DeepAnalysisResult | None:
    try:
        if not init_db():
            return None
        with _connect() as connection:
            row = connection.execute(
                """SELECT result_json FROM deep_analysis_results
                   WHERE candidate_id = ? AND provider = ? AND model = ?
                     AND analysis_version = ?""",
                (candidate_id, provider, model, analysis_version),
            ).fetchone()
        if not row:
            return None
        value = row["result_json"]
        return DeepAnalysisResult.model_validate(value) if isinstance(value, dict) else DeepAnalysisResult.model_validate_json(value)
    except (ValueError, sqlite3.Error):
        return None


def has_software_analysis_result(
    candidate_id: str, provider: str, model: str, analysis_version: str
) -> bool:
    try:
        if not init_db():
            return False
        with _connect() as connection:
            return connection.execute(
                """SELECT 1 FROM software_analysis_results
                   WHERE candidate_id = ? AND provider = ? AND model = ?
                     AND analysis_version = ?""",
                (candidate_id, provider, model, analysis_version),
            ).fetchone() is not None
    except sqlite3.Error:
        return False


def save_software_analysis_result(
    result: SoftwareAnalysisResult, *, force_reanalyze: bool = False
) -> bool:
    try:
        if not init_db():
            return False
        with _connect() as connection:
            sql = """INSERT INTO software_analysis_results (
                candidate_id, provider, model, analysis_version, software_score,
                recommended_next_step, result_json, input_characters,
                input_tokens, output_tokens, total_tokens, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            if force_reanalyze:
                sql += """ ON CONFLICT(candidate_id, provider, model, analysis_version)
                    DO UPDATE SET software_score=excluded.software_score,
                    recommended_next_step=excluded.recommended_next_step,
                    result_json=excluded.result_json,
                    input_characters=excluded.input_characters,
                    input_tokens=excluded.input_tokens,
                    output_tokens=excluded.output_tokens,
                    total_tokens=excluded.total_tokens,
                    updated_at=excluded.updated_at"""
            else:
                sql += " ON CONFLICT(candidate_id, provider, model, analysis_version) DO NOTHING"
            cursor = connection.execute(sql, (
                result.candidate_id, result.provider, result.model,
                result.analysis_version, result.software_score,
                result.recommended_next_step, result.model_dump_json(),
                result.input_characters, result.input_tokens, result.output_tokens,
                result.total_tokens, result.created_at, result.updated_at,
            ))
        return cursor.rowcount == 1
    except (TypeError, ValueError, sqlite3.Error):
        return False


def get_software_analysis_result(
    candidate_id: str, provider: str, model: str, analysis_version: str
) -> SoftwareAnalysisResult | None:
    try:
        if not init_db():
            return None
        with _connect() as connection:
            row = connection.execute(
                """SELECT result_json FROM software_analysis_results
                   WHERE candidate_id = ? AND provider = ? AND model = ?
                     AND analysis_version = ?""",
                (candidate_id, provider, model, analysis_version),
            ).fetchone()
        if not row:
            return None
        value = row["result_json"]
        return SoftwareAnalysisResult.model_validate(value) if isinstance(value, dict) else SoftwareAnalysisResult.model_validate_json(value)
    except (ValueError, sqlite3.Error):
        return None


def _row_to_product(row: sqlite3.Row) -> Product:
    """Convert a database row to Product while preserving an absent image."""
    image_url = row["image_url"]
    product = Product(
        project_id=row["project_id"],
        source_platform=row["source_platform"],
        url=row["url"],
        title=row["title"],
        description=row["description"],
        category=row["category"],
        image_url=image_url or row["url"],
        raw_data=_decode_json(row["raw_data"], {}),
    )
    if not image_url:
        product.image_url = ""
    return product


def is_processed(url: str) -> bool:
    """Return whether a URL has already been marked as processed."""
    try:
        if not init_db():
            return False
        with _connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM processed_projects WHERE url = ?",
                (url,),
            ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False


def mark_processed(url: str) -> bool:
    """Mark a URL as processed without creating duplicate records."""
    try:
        if not init_db():
            return False
        with _connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO processed_projects (url) VALUES (?)",
                (url,),
            )
        return cursor.rowcount == 1
    except sqlite3.Error:
        return False
