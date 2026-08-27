"""SQLite persistence for products and processed project URLs."""

import json
import sqlite3
from datetime import datetime, timezone
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


DATABASE_SETTINGS = get_database_settings()
DB_PATH = DATABASE_SETTINGS.sqlite_path or DEFAULT_SQLITE_PATH


def _decode_json(value, default):
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value) if value else default


def _text_timestamp(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def _connect() -> sqlite3.Connection:
    if DATABASE_SETTINGS.backend == "postgresql":
        from postgres_backend import postgres_connection
        return postgres_connection(DATABASE_SETTINGS.database_url)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> bool:
    """Create the database directory and required tables."""
    try:
        if DATABASE_SETTINGS.backend == "postgresql":
            from postgres_backend import initialize_postgres_schema
            initialize_postgres_schema(DATABASE_SETTINGS.database_url)
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
                """
            )
            _ensure_filter_columns(connection)
            _ensure_lifecycle_columns(connection)
            _ensure_triage_unique_key(connection)
            _ensure_triage_bilingual_columns(connection)
            _ensure_pipeline_stats_column(connection)
        return True
    except (OSError, sqlite3.Error):
        return False


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
) -> tuple[int, int]:
    """Save products in one transaction and count URL duplicates.

    Returns:
        A ``(saved_count, duplicate_count)`` tuple. Database or serialization
        errors are contained and reported as zero saved and zero duplicates.
    """
    if not init_db():
        return 0, 0

    saved_count = 0
    duplicate_count = 0
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
                    _save_metric_snapshot_if_changed(
                        connection, product_id, product.source_platform,
                        product.raw_data, now,
                    )
        return saved_count, duplicate_count
    except (AttributeError, TypeError, ValueError, sqlite3.Error):
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


def save_user_feedback(
    entity_type: str, entity_id: str, feedback_type: str, note: str = ""
) -> bool:
    if entity_type not in {"product", "candidate"} or feedback_type not in {
        "FAVORITE", "WATCH", "NOT_INTERESTED",
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


def save_candidates(
    candidates: list[MicroInnovationCandidate],
) -> tuple[int, int]:
    """Insert candidates without duplicating candidate IDs or source URLs."""
    if not init_db():
        return 0, 0
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
