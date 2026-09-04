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
    render_wxpusher_messages,
    validate_web_wxpusher_parity,
)
from wxpusher_notifier import (
    WxPusherNotifier,
    notification_delivery_key,
    send_full_fidelity_daily,
)


DELIVERY_PURPOSE = "wxpusher_full_fidelity_acceptance"


def validate_snapshot(dataset: dict) -> tuple[list[dict], dict]:
    """Fail closed unless the persisted snapshot is complete and render-safe."""
    items = list(dataset.get("items") or [])
    if not dataset.get("run_id") or not items:
        raise ValueError("persisted Daily snapshot is missing or empty")

    direction_ids = [str(item.get("direction_id") or "") for item in items]
    if any(not value for value in direction_ids) or len(direction_ids) != len(set(direction_ids)):
        raise ValueError("Daily snapshot contains missing or duplicate Direction IDs")

    voice_ids: list[str] = []
    for item in items:
        if not (item.get("name_zh") or item.get("canonical_name_zh")):
            raise ValueError(f"missing Chinese name for Direction {item['direction_id']}")
        if not item.get("description_zh"):
            raise ValueError(f"missing Chinese description for Direction {item['direction_id']}")
        for voice in item.get("user_voice") or []:
            voice_id = str(voice.get("user_voice_id") or "")
            if not voice_id or voice_id in voice_ids:
                raise ValueError("Daily snapshot contains missing or duplicate User Voice IDs")
            voice_ids.append(voice_id)
            if not voice.get("translated_text_zh"):
                raise ValueError(f"missing Chinese User Voice translation: {voice_id}")
            if not voice.get("original_text"):
                raise ValueError(f"missing English User Voice original: {voice_id}")
            if not voice.get("source_url"):
                raise ValueError(f"missing User Voice source URL: {voice_id}")

    messages = render_wxpusher_messages(dataset, max_chars=DEFAULT_WXPUSHER_MAX_CHARS)
    if len(messages) != 1:
        raise ValueError(
            f"acceptance report requires {len(messages)} messages; expected exactly one"
        )
    parity = validate_web_wxpusher_parity(dataset, messages)
    if not parity.get("overall"):
        raise ValueError("Web and WxPusher report parity validation failed")
    return messages, parity


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
