"""Background collection entrypoint; it never composes or delivers Daily."""

from __future__ import annotations

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
    if not db.init_db():
        return False
    run_id = db.start_pipeline_run()
    ok = run_pipeline(run_id=run_id, finish_run=False)
    if ok:
        _persist_user_voice(run_id)
    db.finish_pipeline_run(run_id, "COMPLETED" if ok else "FAILED")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run_collection() else 1)
