"""Production daily orchestration, independent from the Web process."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import os
from pathlib import Path
from time import perf_counter
from typing import Callable

import config
import db
from ai_filter import run_triage_batch
from ai_providers import BaseAIProvider, create_provider
from daily_ranker import (
    OpportunityInput, load_current_opportunities, select_daily_top,
    select_full_qualified, to_triage_candidate,
)
from main import run_pipeline
from performance_timing import query_profile, timed_stage, timing_line
from wxpusher_notifier import (
    DailyNotificationSummary, NotificationTopPick, send_daily_notification,
    send_full_fidelity_daily,
)


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
    opportunities: list[OpportunityInput] | None = None,
    output: Callable[[str], None] = print,
) -> DailyAIResult:
    """Process new candidates first, then re-evaluations and historical backlog."""
    budget = max(1, limit or config.MAX_DAILY_TRIAGE_CALLS)
    result = DailyAIResult(limit=budget)
    if opportunities is None:
        with query_profile(output, "candidate_loading"):
            opportunities = load_current_opportunities()
    new_ids = new_candidate_ids or set()
    with query_profile(output, "backlog_selection"):
        re_evaluations = _re_evaluation_candidates(opportunities)
        commodity = db.get_candidate_commodity()
        existing_triage_ids = db.get_triage_candidate_ids(
            "gemini", config.GEMINI_TRIAGE_MODEL,
        )
        eligible = [
            item for item in opportunities
            if item.candidate_type != "consumer_trend"
            or commodity.get(item.candidate_id, ("", 0))[0] == "PROMISING"
        ]
        missing = [
            item for item in eligible
            if item.candidate_id not in existing_triage_ids
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
    with timed_stage(output, "gemini_total"):
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

                def save_timed(triage_result, force_reanalyze=False):
                    with query_profile(output, "triage_save"):
                        return db.save_triage_result(
                            triage_result, force_reanalyze=force_reanalyze,
                        )

                with timed_stage(
                    output, "gemini_call", candidate_id=item.candidate_id,
                ):
                    batch = run_triage_batch(
                        [to_triage_candidate(item)], products=products, commodity=commodity,
                        provider=provider, has_result=db.has_triage_result,
                        save_result=save_timed, force_reanalyze=force,
                    )
                if batch.processed:
                    triage = batch.processed[0]
                    existing_triage_ids.add(item.candidate_id)
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
        item.candidate_id not in existing_triage_ids
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
    output: Callable[[str], None] = print,
) -> DailyRunResult:
    """Run ingestion, bounded AI backlog coverage, and optional-deep ranking."""
    pipeline_started = perf_counter()
    lock = PipelineLock(lock_path)
    if not lock.acquire():
        return DailyRunResult("", "FAILED", 0, "pipeline already running")
    run_id = ""
    try:
        with query_profile(output, "database_init"):
            if not db.init_db():
                return DailyRunResult("", "FAILED", 0, "database initialization failed")
        with query_profile(output, "candidate_loading_before"):
            before_products = len(db.get_all_product_urls())
            before_opportunities = {item.candidate_id for item in load_current_opportunities()}
        run_id = db.start_pipeline_run()
        step = pipeline_step or (lambda current_id: run_pipeline(
            run_id=current_id, finish_run=False, output=output,
        ))
        with timed_stage(output, "source_ingestion_total"):
            pipeline_ok = step(run_id)
        if not pipeline_ok:
            db.finish_pipeline_run(run_id, "FAILED", "database or pipeline write failed")
            return DailyRunResult(run_id, "FAILED", 0, "database or pipeline write failed")

        with query_profile(output, "candidate_loading_after_ingestion"):
            opportunities = load_current_opportunities()
        new_candidate_ids = {
            item.candidate_id for item in opportunities if item.candidate_id not in before_opportunities
        }
        source_rows, source_failures = _source_summary(run_id)
        try:
            ai_value = ai_step() if ai_step else run_daily_triage(
                new_candidate_ids=new_candidate_ids,
                opportunities=opportunities,
                output=output,
            )
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

        with query_profile(output, "opportunity_loading_post_gemini"):
            ranking_opportunities = load_current_opportunities()
        with timed_stage(output, "ranking"):
            ranking = select_daily_top(
                ranking_opportunities, require_physical_analysis=False,
            )
            qualified = select_full_qualified(ranking_opportunities)
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
            "qualified_count": len(qualified),
            "top_picks": [
                {
                    "title": (
                        item.candidate.triage.display_title_zh
                        if item.candidate.triage and item.candidate.triage.display_title_zh
                        else item.candidate.display_title
                    ),
                    "score": item.final_rank_score,
                    "reason": (
                        item.candidate.triage.primary_reason_zh
                        if item.candidate.triage and item.candidate.triage.primary_reason_zh
                        else item.candidate.triage.primary_reason
                        if item.candidate.triage
                        else item.selection_reason
                    ),
                }
                for item in ranking.final[:3]
            ],
            "sources": source_rows,
        }
        errors = []
        if source_failures:
            errors.append(f"{source_failures} source(s) unavailable")
        if ai.unavailable or ai.failed:
            errors.append("Gemini unavailable for some candidates; AI remains PENDING")
        status = "PARTIAL" if errors else "SUCCESS"
        error = "; ".join(errors)
        with query_profile(output, "pipeline_run_finalization"):
            db.finish_pipeline_run(run_id, status, error, stats=stats)
        try:
            from daily_discovery import build_daily_discovery
            from daily_picks import build_daily_picks
            snapshot = build_daily_discovery(run_id)
            stats["daily_discovery_count"] = snapshot["item_count"]
            daily_picks = build_daily_picks(snapshot, persist=True)
            stats["daily_picks_run_id"] = daily_picks.get("run_id", "")
            stats["daily_picks_count"] = daily_picks.get("item_count", 0)
        except Exception as exc:
            output(f"WARNING: Daily Discovery snapshot unavailable ({type(exc).__name__})")
        return DailyRunResult(run_id, status, ai.pending, error, stats)
    finally:
        lock.release()
        output(timing_line(
            stage="pipeline_total", duration_s=perf_counter() - pipeline_started,
        ))


def main() -> int:
    if os.getenv("PRODUCTION_DAILY", "").casefold() == "true" and db.DATABASE_SETTINGS.backend != "postgresql":
        result = DailyRunResult(
            "", "FAILED", 0, "Production daily runner requires PostgreSQL DATABASE_URL",
        )
    else:
        try:
            result = execute_daily()
        except Exception as exc:
            result = DailyRunResult(
                "", "FAILED", 0, f"Unexpected {type(exc).__name__}",
            )
    source_failures = [
        (str(row.get("source_platform", "unknown")), str(row.get("error", "unavailable")))
        for row in result.stats.get("sources", []) if row.get("failed")
    ]
    triage = result.stats.get("triage", {})
    top_picks = [
        NotificationTopPick(
            str(item.get("title", "Untitled")), int(item.get("score", 0)),
            str(item.get("reason", "")),
        )
        for item in result.stats.get("top_picks", [])[:3]
    ]
    run_url = ""
    if os.getenv("GITHUB_SERVER_URL") and os.getenv("GITHUB_REPOSITORY") and os.getenv("GITHUB_RUN_ID"):
        run_url = (
            f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
            f"/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        )
    if os.getenv("EVIDENCE_FIRST_WXPUSHER_ENABLED", "false").lower() in {"1", "true", "yes"}:
        try:
            persisted = db.get_persisted_daily_picks(run_id=result.stats.get("daily_picks_run_id"))
            if result.status != "FAILED" and persisted:
                send_full_fidelity_daily(
                    persisted, is_delivered=db.is_notification_delivered,
                    record_delivery=db.record_notification_delivery,
                )
            elif result.status == "FAILED":
                send_daily_notification(DailyNotificationSummary(
                    status=result.status, failed_sources=source_failures,
                    failed_stage="Daily Pipeline", error=result.error, run_url=run_url,
                ))
        except Exception as exc:
            print(f"WARNING: WxPusher notification failed ({type(exc).__name__})")
    print(f"Daily Product Picker: {result.status}")
    print(f"AI Pending: {result.ai_pending}")
    if result.error:
        print(result.error)
    return 1 if result.status == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
