"""Fast Daily composition from the persisted evidence pool; never scrapes."""

from __future__ import annotations

import time
import os

import config
import db
from daily_discovery import build_rolling_daily_discovery, build_strict_daily_discovery
from daily_picks import build_daily_picks


def compose_daily(*, persist: bool = True, days: int | None = None, target: int = 20, business_date: str | None = None) -> dict:
    """Build the authoritative Web/WxPusher snapshot without live collection or AI."""
    started = time.perf_counter()
    if not db.init_db():
        raise RuntimeError("database initialization failed")
    discovery = (
        build_rolling_daily_discovery(days=days or config.DAILY_EVIDENCE_FRESHNESS_DAYS, persist=persist)
        if config.DAILY_FALLBACK_ENABLED else
        build_strict_daily_discovery(business_date=business_date, persist=persist)
    )
    result = build_daily_picks(discovery, persist=persist, target=target)
    result["compose_runtime_seconds"] = time.perf_counter() - started
    result["live_fetch_calls"] = 0
    result["gemini_calls"] = 0
    result["business_date"] = discovery["discovery_date"]
    result["window_start"] = discovery.get("window_start")
    result["window_end"] = discovery.get("window_end")
    result["fallback_enabled"] = config.DAILY_FALLBACK_ENABLED
    result["source_failures"] = discovery.get("source_failures", [])
    return result


def deliver_persisted_daily(result: dict) -> bool:
    """Validate and deliver the exact persisted snapshot, idempotently."""
    from daily_direction_report import validate_notification_snapshot
    from wxpusher_notifier import WxPusherNotifier, send_full_fidelity_daily
    persisted = db.get_persisted_daily_picks(run_id=result.get("run_id"))
    if not persisted:
        return False
    validate_notification_snapshot(persisted)
    sender = WxPusherNotifier.from_env()
    return send_full_fidelity_daily(
        persisted, notifier=sender, is_delivered=db.is_notification_delivered,
        record_delivery=db.record_notification_delivery,
    )


def main() -> int:
    started = time.perf_counter()
    print("DAILY_COMPOSE_START")
    result = compose_daily(business_date=os.getenv("PRODUCT_PICKER_DISCOVERY_DATE") or None)
    diagnostics = result["diagnostics"]
    for key, value in (
        ("business_date", result["business_date"]), ("window_start", result.get("window_start")),
        ("window_end", result.get("window_end")), ("fallback_enabled", str(result["fallback_enabled"]).lower()),
        ("eligible_current_window_identities", diagnostics["eligible_identities"]),
        ("eligible_current_window_families", diagnostics["eligible_families"]),
        ("candidate_directions", diagnostics["candidate_directions"]),
        ("selected_directions", result["item_count"]), ("source_distribution", diagnostics["source_distribution"]),
        ("category_distribution", diagnostics["category_distribution"]),
        ("user_voice_count", diagnostics["user_voice_count"]),
        ("missing_chinese_count", diagnostics["missing_chinese_translation_count"]),
        ("quality", result["quality_status"]),
        ("source_failures", result["source_failures"]),
    ):
        print(f"{key}={value}")
    print(f"DAILY_PERSISTED daily_run_id={result.get('run_id')}")
    if os.getenv("EVIDENCE_FIRST_WXPUSHER_ENABLED", "false").casefold() == "true":
        print("WXPUSHER_START")
        delivered = deliver_persisted_daily(result)
        print(f"WXPUSHER_RESULT status={'sent_or_idempotent' if delivered else 'failed'}")
    print(f"Daily composition: {result['quality_status']}")
    print(f"Directions: {result['item_count']}")
    print(f"DAILY_COMPOSE_END runtime_s={time.perf_counter() - started:.3f}")
    return 0 if result["quality_status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
