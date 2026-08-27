"""Read-only dashboard queries and persistent user actions for the local app."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from typing import Iterable, TypeVar

import db
from software_analysis import stable_candidate_id
from models import Product
from product_display import SourceMetadata, extract_source_metadata, product_summary, product_summary_zh


SOURCE_LABELS = {
    "reddit_arctic_shift": "Reddit",
    "reddit": "Reddit",
    "amazon": "Amazon",
    "kickstarter": "Kickstarter",
    "indiegogo": "Indiegogo",
    "yanko_design": "Yanko Design",
    "product_hunt": "Product Hunt",
}
AI_STATUSES = ("PASS", "REVIEW", "REJECT", "AI_PENDING", "NOT_ANALYZED")
MANUAL_STATUSES = ("FAVORITE", "WATCH", "NOT_INTERESTED")
T = TypeVar("T")


@dataclass
class DashboardProduct:
    id: int
    project_id: str
    source_platform: str
    source: str
    url: str
    title: str
    description: str
    product_summary: str
    product_summary_zh: str
    source_metadata: SourceMetadata
    category: str
    first_seen_at: str
    last_seen_at: str
    opportunity_type: str
    record_role: str
    candidate_id: str
    candidate_type: str
    candidate_score: int | None
    theme: str
    rule_status: str
    rule_reason: str
    feasibility_status: str
    feasibility_reason: str
    commodity_status: str
    commodity_reason: str
    specificity_status: str
    specificity_reason: str
    gemini_status: str
    gemini_score: int | None
    gemini_reason: str
    gemini_opportunity: str
    gemini_risks: list[str]
    display_title_zh: str
    gemini_reason_zh: str
    gemini_opportunity_zh: str
    gemini_risks_zh: list[str]
    manual_status: str
    deep_analysis: dict | None = None
    software_analysis: dict | None = None
    metric_history: list[dict] = field(default_factory=list)

    @property
    def display_type(self) -> str:
        if self.record_role == "software" or self.opportunity_type == "software":
            return "software"
        if self.candidate_type == "inspiration_product" or self.opportunity_type == "inspiration":
            return "inspiration"
        return "physical"

    @property
    def rejected(self) -> bool:
        return (
            self.rule_status == "rejected"
            or self.feasibility_status == "REJECT"
            or self.commodity_status == "COMMODITY"
            or self.specificity_status == "TOO_BROAD"
            or self.gemini_status in {"REVIEW", "REJECT"}
        )


@dataclass(frozen=True)
class ProductFilters:
    keyword: str = ""
    sources: tuple[str, ...] = ()
    date_range: str = "all"
    product_types: tuple[str, ...] = ()
    rule_statuses: tuple[str, ...] = ()
    feasibility_statuses: tuple[str, ...] = ()
    commodity_statuses: tuple[str, ...] = ()
    specificity_statuses: tuple[str, ...] = ()
    gemini_statuses: tuple[str, ...] = ()
    manual_statuses: tuple[str, ...] = ()
    rejected_only: bool = False


@dataclass
class DashboardSnapshot:
    products: list[DashboardProduct]
    pipeline_sources: list[dict]
    re_evaluation_queue: list[dict]


def _json(value: str | None, default):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value) if value else default
    except (TypeError, json.JSONDecodeError):
        return default


def _analysis_summary(value: str | None) -> dict | None:
    data = _json(value, None)
    if not isinstance(data, dict):
        return None
    allowed = (
        "opportunity_summary", "customer_problem", "existing_solution_gap",
        "deep_score", "software_score", "recommended_next_step",
        "biggest_risks", "main_risks",
    )
    return {key: data[key] for key in allowed if key in data}


def _timestamp(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def load_dashboard_snapshot() -> DashboardSnapshot:
    """Load the complete dashboard state with a small, fixed query count."""
    # Local SQLite initializes lazily. Cloud schema is created only by the
    # explicit migration/deployment step, never by opening the Web app.
    if db.DATABASE_SETTINGS.backend == "sqlite":
        db.init_db()
    with db._connect() as connection:
        product_rows = connection.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
        candidate_rows = connection.execute(
            "SELECT * FROM micro_innovation_candidates ORDER BY candidate_score DESC, id"
        ).fetchall()
        triage_rows = connection.execute(
            """SELECT * FROM ai_triage_results
               WHERE provider='gemini' AND model='gemini-3.5-flash-lite'"""
        ).fetchall()
        specificity_rows = connection.execute(
            """SELECT s.* FROM specificity_results s
               JOIN (SELECT candidate_id, MAX(evaluated_at) evaluated_at
                     FROM specificity_results GROUP BY candidate_id) latest
                 ON latest.candidate_id=s.candidate_id AND latest.evaluated_at=s.evaluated_at"""
        ).fetchall()
        feedback_rows = connection.execute("SELECT * FROM user_product_feedback").fetchall()
        metric_rows = connection.execute(
            "SELECT * FROM product_metric_snapshots ORDER BY product_id, id"
        ).fetchall()
        deep_rows = connection.execute(
            """SELECT d.* FROM deep_analysis_results d
               JOIN (SELECT candidate_id, MAX(updated_at) updated_at FROM deep_analysis_results GROUP BY candidate_id) latest
                 ON latest.candidate_id=d.candidate_id AND latest.updated_at=d.updated_at"""
        ).fetchall()
        software_rows = connection.execute(
            """SELECT d.* FROM software_analysis_results d
               JOIN (SELECT candidate_id, MAX(updated_at) updated_at FROM software_analysis_results GROUP BY candidate_id) latest
                 ON latest.candidate_id=d.candidate_id AND latest.updated_at=d.updated_at"""
        ).fetchall()
        latest_run = connection.execute(
            "SELECT run_id, started_at, finished_at, status FROM pipeline_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        pipeline_rows = connection.execute(
            "SELECT * FROM pipeline_source_runs WHERE run_id=? ORDER BY id",
            (latest_run["run_id"],),
        ).fetchall() if latest_run else []
        queue_rows = connection.execute(
            """SELECT entity_type, entity_id, note, status, created_at, updated_at
               FROM re_evaluation_requests WHERE status='PENDING' ORDER BY created_at DESC"""
        ).fetchall()

    candidates_by_url = {row["source_url"]: row for row in candidate_rows}
    triage_by_id = {row["candidate_id"]: row for row in triage_rows}
    specificity_by_id = {row["candidate_id"]: row for row in specificity_rows}
    feedback = {(row["entity_type"], row["entity_id"]): row["feedback_type"] for row in feedback_rows}
    metrics: dict[int, list[dict]] = {}
    for row in metric_rows:
        metrics.setdefault(row["product_id"], []).append({
            "captured_at": row["captured_at"],
            "metric_type": row["metric_type"],
            **_json(row["metric_data"], {}),
        })
    deep = {row["candidate_id"]: _analysis_summary(row["result_json"]) for row in deep_rows}
    software = {row["candidate_id"]: _analysis_summary(row["result_json"]) for row in software_rows}

    products = []
    for row in product_rows:
        raw_data = _json(row["raw_data"], {})
        display_metadata = dict(raw_data)
        if row["source_platform"] in {"reddit", "reddit_arctic_shift", "yanko_design"}:
            display_metadata.setdefault("excerpt", row["description"] or "")
        candidate = candidates_by_url.get(row["url"])
        is_software = row["record_role"] == "software" or row["opportunity_type"] == "software"
        if is_software:
            product_for_id = Product(
                project_id=row["project_id"], source_platform=row["source_platform"],
                url=row["url"], title=row["title"], description=row["description"] or "",
                category=row["category"] or "uncategorized", image_url=row["image_url"] or row["url"],
                raw_data=_json(row["raw_data"], {}),
            )
            candidate_id = stable_candidate_id(product_for_id)
            candidate_type = "software"
            candidate_score = row["filter_score"]
        else:
            candidate_id = candidate["candidate_id"] if candidate else ""
            candidate_type = candidate["candidate_type"] if candidate else ""
            candidate_score = candidate["candidate_score"] if candidate else None
        triage = triage_by_id.get(candidate_id)
        specificity = specificity_by_id.get(candidate_id)
        risks = _json(triage["main_risks"], []) if triage else []
        manual = feedback.get(("product", str(row["id"])), "")
        if not manual and candidate_id:
            manual = feedback.get(("candidate", candidate_id), "")
        theme = candidate_type if candidate_type == "inspiration_product" else (row["category"] or "uncategorized")
        products.append(DashboardProduct(
            id=row["id"], project_id=row["project_id"],
            source_platform=row["source_platform"],
            source=SOURCE_LABELS.get(row["source_platform"], row["source_platform"].replace("_", " ").title()),
            url=row["url"], title=row["title"] or "Untitled",
            description=row["description"] or "",
            product_summary=product_summary(row["description"], raw_data, row["title"] or ""),
            product_summary_zh=product_summary_zh(raw_data),
            source_metadata=extract_source_metadata(row["source_platform"], display_metadata),
            category=row["category"] or "uncategorized",
            first_seen_at=_timestamp(row["first_seen_at"] or row["created_at"]),
            last_seen_at=_timestamp(row["last_seen_at"] or row["created_at"]),
            opportunity_type=row["opportunity_type"] or "uncertain",
            record_role=row["record_role"] or "uncertain", candidate_id=candidate_id,
            candidate_type=candidate_type, candidate_score=candidate_score, theme=theme,
            rule_status=row["filter_status"] or "", rule_reason=row["filter_reason"] or "",
            feasibility_status=row["feasibility_status"] or "",
            feasibility_reason=row["feasibility_reason"] or "",
            commodity_status=row["commodity_status"] or "",
            commodity_reason=row["commodity_reason"] or "",
            specificity_status=specificity["specificity_status"] if specificity else "",
            specificity_reason=specificity["specificity_reason"] if specificity else "",
            gemini_status=(triage["triage_status"] if triage else (
                "AI_PENDING" if candidate_id else "NOT_ANALYZED"
            )),
            gemini_score=triage["triage_score"] if triage else None,
            gemini_reason=triage["primary_reason"] if triage else "",
            gemini_opportunity=triage["key_opportunity"] if triage else "",
            gemini_risks=risks, manual_status=manual,
            display_title_zh=(triage["display_title_zh"] or "") if triage else "",
            gemini_reason_zh=(triage["primary_reason_zh"] or "") if triage else "",
            gemini_opportunity_zh=(triage["key_opportunity_zh"] or "") if triage else "",
            gemini_risks_zh=_json(triage["main_risks_zh"], []) if triage else [],
            deep_analysis=deep.get(candidate_id), software_analysis=software.get(candidate_id),
            metric_history=metrics.get(row["id"], []),
        ))

    run_info = dict(latest_run) if latest_run else {}
    pipeline_sources = [dict(row) | {"run": run_info} for row in pipeline_rows]
    return DashboardSnapshot(products, pipeline_sources, [dict(row) for row in queue_rows])


def get_all_products_dashboard() -> list[DashboardProduct]:
    """Return every product for the All Products page without qualification filters.

    Products are loaded as the primary dataset. Candidate, Gemini, specificity,
    feedback, and analysis records only enrich matching products and never
    determine whether a product is returned.
    """
    return load_dashboard_snapshot().products


def page_records(items: list[T], page: int = 1, page_size: int = 50) -> list[T]:
    """Return one bounded page without changing or filtering the input."""
    safe_page = max(1, page)
    start = (safe_page - 1) * page_size
    return items[start:start + page_size]


def filter_products(products: Iterable[DashboardProduct], filters: ProductFilters) -> list[DashboardProduct]:
    """Apply deterministic in-memory dashboard filters to one loaded snapshot."""
    output = list(products)
    keyword = filters.keyword.strip().casefold()
    if keyword:
        output = [p for p in output if keyword in f"{p.title} {p.description} {p.category} {p.theme}".casefold()]
    if filters.sources:
        selected = set(filters.sources)
        output = [p for p in output if p.source in selected or p.source_platform in selected]
    if filters.product_types:
        output = [p for p in output if p.display_type in set(filters.product_types)]
    if filters.rule_statuses:
        output = [p for p in output if p.rule_status in set(filters.rule_statuses)]
    if filters.feasibility_statuses:
        output = [p for p in output if p.feasibility_status in set(filters.feasibility_statuses)]
    if filters.commodity_statuses:
        output = [p for p in output if p.commodity_status in set(filters.commodity_statuses)]
    if filters.specificity_statuses:
        output = [p for p in output if p.specificity_status in set(filters.specificity_statuses)]
    if filters.gemini_statuses:
        output = [p for p in output if p.gemini_status in set(filters.gemini_statuses)]
    if filters.manual_statuses:
        output = [p for p in output if p.manual_status in set(filters.manual_statuses)]
    if filters.rejected_only:
        output = [p for p in output if p.rejected]
    days = {"today": 0, "7d": 7, "30d": 30}.get(filters.date_range)
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        output = [p for p in output if _at_or_after(p.first_seen_at, cutoff, today=days == 0)]
    return output


def _at_or_after(value: str, cutoff: datetime, *, today: bool = False) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.date() == cutoff.date() if today else parsed >= cutoff
    except (AttributeError, ValueError):
        return False


def save_manual_status(product_id: int, status: str) -> bool:
    return db.save_user_feedback("product", str(product_id), status)


def clear_manual_status(product_id: int) -> bool:
    try:
        with db._connect() as connection:
            connection.execute(
                "DELETE FROM user_product_feedback WHERE entity_type='product' AND entity_id=?",
                (str(product_id),),
            )
        return True
    except sqlite3.Error:
        return False


def enqueue_re_evaluation(product_id: int, note: str = "") -> bool:
    return db.request_re_evaluation("product", str(product_id), note)
