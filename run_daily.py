"""Stable background entry point, independent from the Web process."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Callable

import config
import db
from ai_providers import create_provider
from daily_ranker import load_current_opportunities
from main import run_pipeline
from phase96 import missing_coverage, run_coverage


LOCK_PATH = Path(__file__).resolve().parent / "data" / "daily_pipeline.lock"


@dataclass(frozen=True)
class DailyRunResult:
    run_id: str
    status: str
    ai_pending: int
    error: str = ""


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


def _default_ai_step() -> int:
    opportunities = load_current_opportunities()
    missing = missing_coverage(opportunities)
    if not missing or not config.is_gemini_configured():
        return len(missing)
    provider = create_provider(
        "gemini", api_key=config.GEMINI_API_KEY, model=config.GEMINI_TRIAGE_MODEL,
    )
    run_coverage(missing, provider=provider, batch_size=10)
    return len(missing_coverage(load_current_opportunities()))


def execute_daily(
    *,
    pipeline_step: Callable[[str], bool] | None = None,
    ai_step: Callable[[], int] | None = None,
    lock_path: Path = LOCK_PATH,
) -> DailyRunResult:
    """Run ingestion then AI; AI failure leaves products intact and marks PARTIAL."""
    lock = PipelineLock(lock_path)
    if not lock.acquire():
        return DailyRunResult("", "FAILED", 0, "pipeline already running")
    run_id = ""
    try:
        if not db.init_db():
            return DailyRunResult("", "FAILED", 0, "database initialization failed")
        run_id = db.start_pipeline_run()
        step = pipeline_step or (lambda current_id: run_pipeline(run_id=current_id, finish_run=False))
        if not step(run_id):
            db.finish_pipeline_run(run_id, "FAILED", "pipeline failed")
            return DailyRunResult(run_id, "FAILED", 0, "pipeline failed")
        with db._connect() as connection:
            source_rows = connection.execute(
                "SELECT failed FROM pipeline_source_runs WHERE run_id = ?", (run_id,)
            ).fetchall()
        source_failures = sum(bool(row["failed"]) for row in source_rows)
        if source_rows and source_failures == len(source_rows):
            db.finish_pipeline_run(run_id, "FAILED", "all sources failed")
            return DailyRunResult(run_id, "FAILED", 0, "all sources failed")
        try:
            pending = (ai_step or _default_ai_step)()
            status = "PARTIAL" if pending or source_failures else "SUCCESS"
            errors = []
            if source_failures:
                errors.append(f"{source_failures} source(s) unavailable")
            if pending:
                errors.append("Gemini unavailable; AI results remain PENDING")
            error = "; ".join(errors)
        except Exception as exc:
            pending = len(missing_coverage(load_current_opportunities()))
            status = "PARTIAL"
            error = f"Gemini unavailable; AI results remain PENDING ({type(exc).__name__})"
        db.finish_pipeline_run(run_id, status, error)
        return DailyRunResult(run_id, status, pending, error)
    finally:
        lock.release()


def main() -> int:
    result = execute_daily()
    print(f"Daily Product Picker: {result.status}")
    print(f"AI Pending: {result.ai_pending}")
    if result.error:
        print(result.error)
    return 1 if result.status == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
