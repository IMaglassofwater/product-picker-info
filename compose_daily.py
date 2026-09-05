"""Fast Daily composition from the persisted evidence pool; never scrapes."""

from __future__ import annotations

import time

import config
import db
from daily_discovery import build_rolling_daily_discovery
from daily_picks import build_daily_picks


def compose_daily(*, persist: bool = True, days: int | None = None, target: int = 20) -> dict:
    """Build the authoritative Web/WxPusher snapshot without live collection or AI."""
    started = time.perf_counter()
    if not db.init_db():
        raise RuntimeError("database initialization failed")
    discovery = build_rolling_daily_discovery(
        days=days or config.DAILY_EVIDENCE_FRESHNESS_DAYS, persist=persist,
    )
    result = build_daily_picks(discovery, persist=persist, target=target)
    result["compose_runtime_seconds"] = time.perf_counter() - started
    result["live_fetch_calls"] = 0
    result["gemini_calls"] = 0
    return result


def main() -> int:
    result = compose_daily()
    print(f"Daily composition: {result['quality_status']}")
    print(f"Directions: {result['item_count']}")
    return 0 if result["quality_status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
