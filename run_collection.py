"""Background collection entrypoint; it never composes or delivers Daily."""

from __future__ import annotations

from time import perf_counter
import db
from main import run_pipeline
from user_voice import extract_user_voice


def _persist_user_voice(run_id: str) -> tuple[int, int]:
    voice = []
    for family in db.get_daily_discovery(run_id):
        for item in extract_user_voice(family):
            item["product_family_id"] = int(family["family_id"])
            voice.append(item)
    return db.save_user_voice_items(voice)


def run_collection() -> bool:
    started = perf_counter()
    print("COLLECTION_START")
    if not db.init_db():
        return False
    run_id = db.start_pipeline_run()
    print(f"run_id={run_id}")
    ok = run_pipeline(run_id=run_id, finish_run=False)
    source_failures = db.get_pipeline_source_failure_count(run_id)
    if ok:
        voice_saved, voice_existing = _persist_user_voice(run_id)
        print(f"USER_VOICE_PERSISTED saved={voice_saved} existing={voice_existing}")
    status = "FAILED" if not ok else "PARTIAL" if source_failures else "COMPLETED"
    db.finish_pipeline_run(run_id, status)
    print(f"COLLECTION_END run_id={run_id} status={status} source_failures={source_failures} runtime_s={perf_counter() - started:.3f}")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run_collection() else 1)
