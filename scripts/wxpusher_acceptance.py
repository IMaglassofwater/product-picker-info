"""Send one idempotent full-fidelity WxPusher acceptance report."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db
from daily_direction_report import (
    DEFAULT_WXPUSHER_MAX_CHARS,
    validate_notification_snapshot,
)
from wxpusher_notifier import (
    ACCEPTANCE_DELIVERY_CHANNEL,
    WxPusherNotifier,
    notification_delivery_key,
    send_full_fidelity_daily,
)


DELIVERY_PURPOSE = ACCEPTANCE_DELIVERY_CHANNEL


def validate_snapshot(dataset: dict) -> tuple[list[dict], dict]:
    """Fail closed unless the persisted snapshot is complete and render-safe."""
    return validate_notification_snapshot(
        dataset,
        max_chars=DEFAULT_WXPUSHER_MAX_CHARS,
        require_single_message=True,
    )


def run_acceptance(*, notifier: WxPusherNotifier | None = None) -> dict:
    """Attempt at most one send and persist only purpose-specific delivery metadata."""
    dataset = db.get_persisted_daily_picks()
    messages, parity = validate_snapshot(dataset or {})
    sender = notifier or WxPusherNotifier.from_env()
    if not sender.configured:
        raise RuntimeError("WxPusher credentials are not configured")

    run_id = str(dataset["run_id"])
    delivery_key, _recipient_hash = notification_delivery_key(
        run_id, sender.uid, channel=DELIVERY_PURPOSE
    )
    existing_status = db.get_notification_delivery_status(delivery_key)
    if existing_status == "DELIVERED":
        return {
            "daily_run_id": run_id,
            "directions": len(dataset["items"]),
            "characters": messages[0]["character_count"],
            "utf8_bytes": messages[0]["utf8_bytes"],
            "messages_required": 1,
            "already_delivered": True,
            "messages_sent": 0,
            "delivery": "SUCCESS",
            "parity": bool(parity["overall"]),
        }
    if existing_status:
        raise RuntimeError(
            "a prior acceptance delivery attempt is unresolved; manual review is required"
        )

    warnings: list[str] = []
    sender._warning = warnings.append

    def purpose_is_delivered(_default_key: str) -> bool:
        return db.is_notification_delivered(delivery_key)

    def purpose_record(
        _default_key: str,
        daily_run_id: str,
        recipient_hash: str,
        chunk_count: int,
        delivered_chunks: int,
    ) -> None:
        db.record_notification_delivery(
            delivery_key,
            daily_run_id,
            recipient_hash,
            chunk_count,
            delivered_chunks,
        )

    success = send_full_fidelity_daily(
        dataset,
        notifier=sender,
        is_delivered=purpose_is_delivered,
        record_delivery=purpose_record,
        max_chars=DEFAULT_WXPUSHER_MAX_CHARS,
    )
    ambiguous = any(
        marker in warning.lower()
        for warning in warnings
        for marker in ("timeout", "requestexception", "connectionerror")
    )
    return {
        "daily_run_id": run_id,
        "directions": len(dataset["items"]),
        "characters": messages[0]["character_count"],
        "utf8_bytes": messages[0]["utf8_bytes"],
        "messages_required": 1,
        "already_delivered": False,
        "messages_sent": 1 if success else 0,
        "delivery": "SUCCESS" if success else ("AMBIGUOUS" if ambiguous else "FAILED"),
        "manual_review_required": ambiguous,
        "parity": bool(parity["overall"]),
        "warnings": warnings,
    }


def main() -> int:
    try:
        result = run_acceptance()
    except Exception as exc:
        print(json.dumps({"delivery": "FAILED", "error_type": type(exc).__name__, "message": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["delivery"] == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
