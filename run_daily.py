"""Production daily orchestration, independent from the Web process."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import os
from pathlib import Path
from typing import Callable

import config
import db
from ai_filter import run_triage_batch
from ai_providers import BaseAIProvider, create_provider
from daily_ranker import OpportunityInput, load_current_opportunities, select_daily_top, to_triage_candidate
from main import run_pipeline


LOCK_PATH = Path(__file__).resolve().parent / "data" / "daily_pipeline.lock"


@dataclass
class DailyAIResult:
    limit: int
    selected: int = 0
    calls: int = 0
    successful: int = 0
    failed: int = 0
    skipped_existing: int = 0
    pending: int = 0
    new_selected: int = 0
    backlog_selected: int = 0
    re_evaluated: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    unavailable: bool = False
    statuses: Counter = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DailyRunResult:
    run_id: str
    status: str
    ai_pending: int
    error: str = ""
    stats: dict = field(default_factory=dict)


class PipelineLock:
    def __init__(self, path: Path = LOCK_PATH):
        self.path = path
        self.acquired = False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        self.acquired = True
        return True

    def release(self) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)
            self.acquired = False


def _re_evaluation_candidates(opportunities: list[OpportunityInput]) -> dict[str, int]:
    by_candidate = {item.candidate_id: item for item in opportunities}
    by_url = {item.source_url: item for item in opportunities}
    with db._connect() as connection:
        products = {
            str(row["id"]): row["url"]
            for row in connection.execute("SELECT id, url FROM products").fetchall()
        }
    selected: dict[str, int] = {}
    for request in db.get_pending_re_evaluations():
        candidate = None
        if request["entity_type"] == "candidate":
            candidate = by_candidate.get(request["entity_id"])
        elif request["entity_type"] == "product":
            candidate = by_url.get(products.get(request["entity_id"], ""))
        if candidate:
            selected[candidate.candidate_id] = request["id"]
    return selected


def run_daily_triage(
    *, new_candidate_ids: set[str] | None = None,
    limit: int | None = None,
    provider: BaseAIProvider | None = None,
) -> DailyAIResult:
    """Process new candidates first, then re-evaluations and historical backlog."""
    budget = max(1, limit or config.MAX_DAILY_TRIAGE_CALLS)
    result = DailyAIResult(limit=budget)
    opportunities = load_current_opportunities()
    new_ids = new_candidate_ids or set()
    re_evaluations = _re_evaluation_candidates(opportunities)
    commodity = db.get_candidate_commodity()
    eligible = [
        item for item in opportunities
        if item.candidate_type != "consumer_trend"
        or commodity.get(item.candidate_id, ("", 0))[0] == "PROMISING"
    ]
    missing = [
        item for item in eligible
        if not db.has_triage_result(item.candidate_id, "gemini", config.GEMINI_TRIAGE_MODEL)
    ]
    result.skipped_existing = len(eligible) - len(missing)
    if provider is None:
        if not config.is_gemini_configured():
            result.unavailable = True
            result.pending = len(missing)
            result.errors.append("Gemini is not configured")
            return result
        try:
            provider = create_provider(
                "gemini", api_key=config.GEMINI_API_KEY, model=config.GEMINI_TRIAGE_MODEL,
            )
        except Exception as exc:
            result.unavailable = True
            result.pending = len(missing)
            result.errors.append(f"Gemini provider unavailable ({type(exc).__name__})")
            return result

    products = {product.url: product for product in db.get_all_products()}
    new_group = sorted(
        (item for item in missing if item.candidate_id in new_ids),
        key=lambda item: (-item.candidate_score, item.candidate_id),
    )
    re_evaluate_group = sorted(
        (item for item in eligible if item.candidate_id in re_evaluations and item.candidate_id not in new_ids),
        key=lambda item: (-item.candidate_score, item.candidate_id),
    )
    reserved = {item.candidate_id for item in new_group + re_evaluate_group}
    backlog_group = sorted(
        (item for item in missing if item.candidate_id not in reserved),
        key=lambda item: (-item.candidate_score, item.candidate_id),
    )

    calls_before = getattr(provider, "api_calls_sent", 0)
    for group_name, group, force in (
        ("new", new_group, False),
        ("re_evaluate", re_evaluate_group, True),
        ("backlog", backlog_group, False),
    ):
        for item in group:
            if result.selected >= budget:
                break
            result.selected += 1
            result.new_selected += int(group_name == "new")
            result.backlog_selected += int(group_name == "backlog")
            batch = run_triage_batch(
                [to_triage_candidate(item)], products=products, commodity=commodity,
                provider=provider, has_result=db.has_triage_result,
                save_result=db.save_triage_result, force_reanalyze=force,
            )
            if batch.processed:
                triage = batch.processed[0]
                result.successful += 1
                result.statuses[triage.triage_status] += 1
                if force:
                    request_id = re_evaluations.get(item.candidate_id)
                    result.re_evaluated += int(bool(request_id and db.complete_re_evaluation(request_id)))
            else:
                result.failed += 1
                result.errors.append(f"{item.candidate_id}: Gemini triage failed")
        if result.selected >= budget:
            break

    result.calls = max(0, getattr(provider, "api_calls_sent", 0) - calls_before)
    usage = getattr(provider, "usage", {})
    result.input_tokens = int(usage.get("input_tokens", 0) or 0)
    result.output_tokens = int(usage.get("output_tokens", 0) or 0)
    result.total_tokens = int(usage.get("total_tokens", 0) or 0)
    result.pending = sum(
        not db.has_triage_result(item.candidate_id, "gemini", config.GEMINI_TRIAGE_MODEL)
        for item in eligible
    )
    return result


def _source_summary(run_id: str) -> tuple[list[dict], int]:
    with db._connect() as connection:
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM pipeline_source_runs WHERE run_id=? ORDER BY id", (run_id,)
        ).fetchall()]
    return rows, sum(bool(row["failed"]) for row in rows)


def execute_daily(
    *, pipeline_step: Callable[[str], bool] | None = None,
    ai_step: Callable[[], int | DailyAIResult] | None = None,
    lock_path: Path = LOCK_PATH,
) -> DailyRunResult:
    """Run ingestion, bounded AI backlog coverage, and optional-deep ranking."""
    lock = PipelineLock(lock_path)
    if not lock.acquire():
        return DailyRunResult("", "FAILED", 0, "pipeline already running")
    run_id = ""
    try:
        if not db.init_db():
            return DailyRunResult("", "FAILED", 0, "database initialization failed")
        before_products = len(db.get_all_product_urls())
        before_opportunities = {item.candidate_id for item in load_current_opportunities()}
        run_id = db.start_pipeline_run()
        step = pipeline_step or (lambda current_id: run_pipeline(run_id=current_id, finish_run=False))
        if not step(run_id):
            db.finish_pipeline_run(run_id, "FAILED", "database or pipeline write failed")
            return DailyRunResult(run_id, "FAILED", 0, "database or pipeline write failed")

        opportunities = load_current_opportunities()
        new_candidate_ids = {
            item.candidate_id for item in opportunities if item.candidate_id not in before_opportunities
        }
        source_rows, source_failures = _source_summary(run_id)
        try:
            ai_value = ai_step() if ai_step else run_daily_triage(new_candidate_ids=new_candidate_ids)
            ai = ai_value if isinstance(ai_value, DailyAIResult) else DailyAIResult(
                config.MAX_DAILY_TRIAGE_CALLS, pending=int(ai_value)
            )
        except Exception as exc:
            ai = DailyAIResult(config.MAX_DAILY_TRIAGE_CALLS, unavailable=True)
            ai.pending = sum(
                not db.has_triage_result(item.candidate_id, "gemini", config.GEMINI_TRIAGE_MODEL)
                for item in load_current_opportunities()
            )
            ai.errors.append(f"Gemini unavailable ({type(exc).__name__})")

        ranking = select_daily_top(load_current_opportunities(), require_physical_analysis=False)
        stats = {
            "products_before": before_products,
            "products_after": len(db.get_all_product_urls()),
            "new_products": sum(row["new_count"] for row in source_rows),
            "updated_products": sum(row["updated_count"] for row in source_rows),
            "candidates": len(opportunities),
            "triage": {
                key: value for key, value in asdict(ai).items() if key not in {"statuses", "errors"}
            } | {"statuses": dict(ai.statuses), "errors": ai.errors[:10]},
            "ranking_count": len(ranking.final),
            "sources": source_rows,
        }
        errors = []
        if source_failures:
            errors.append(f"{source_failures} source(s) unavailable")
        if ai.unavailable or ai.failed:
            errors.append("Gemini unavailable for some candidates; AI remains PENDING")
        status = "PARTIAL" if errors else "SUCCESS"
        error = "; ".join(errors)
        db.finish_pipeline_run(run_id, status, error, stats=stats)
        return DailyRunResult(run_id, status, ai.pending, error, stats)
    finally:
        lock.release()


def main() -> int:
    if os.getenv("PRODUCTION_DAILY", "").casefold() == "true" and db.DATABASE_SETTINGS.backend != "postgresql":
        print("Daily Product Picker: FAILED")
        print("Production daily runner requires PostgreSQL DATABASE_URL")
        return 1
    result = execute_daily()
    print(f"Daily Product Picker: {result.status}")
    print(f"AI Pending: {result.ai_pending}")
    if result.error:
        print(result.error)
    return 1 if result.status == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
