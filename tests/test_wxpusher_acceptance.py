from __future__ import annotations

import pytest

from scripts import wxpusher_acceptance as acceptance


def snapshot() -> dict:
    return {
        "run_id": "picks:daily:test",
        "items": [{
            "direction_id": "direction:1",
            "pick_order": 1,
            "name_zh": "收纳袋",
            "name_en": "Organizer Pouch",
            "description_zh": "用于收纳小件物品。",
            "representative_products": ["Simple Pouch"],
            "source_evidence": [{
                "evidence_id": "evidence:1", "source": "Reddit",
                "product_name": "Simple Pouch", "facts": ["public post"],
                "url": "https://example.com/product",
            }],
            "user_voice": [{
                "user_voice_id": "voice:1", "source": "Reddit",
                "translated_text_zh": "希望拉链更顺滑。",
                "original_text": "I wish the zipper were smoother.",
                "source_url": "https://example.com/comment", "author": "public-user",
            }],
        }],
    }


class Sender:
    configured = True
    uid = "UID-safe-test"

    def __init__(self):
        self._warning = lambda _value: None


def test_validate_snapshot_requires_complete_bilingual_voice():
    messages, parity = acceptance.validate_snapshot(snapshot())
    assert len(messages) == 1
    assert parity["overall"] is True
    broken = snapshot()
    broken["items"][0]["user_voice"][0]["original_text"] = ""
    with pytest.raises(ValueError, match="English User Voice original"):
        acceptance.validate_snapshot(broken)


def test_acceptance_uses_purpose_specific_idempotency(monkeypatch):
    data = snapshot()
    monkeypatch.setattr(acceptance.db, "get_persisted_daily_picks", lambda: data)
    expected_key, _ = acceptance.notification_delivery_key(
        data["run_id"], Sender.uid, channel=acceptance.DELIVERY_PURPOSE
    )
    checked: list[str] = []
    monkeypatch.setattr(
        acceptance.db,
        "get_notification_delivery_status",
        lambda key: checked.append(key) is None and "DELIVERED",
    )
    monkeypatch.setattr(
        acceptance,
        "send_full_fidelity_daily",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not send")),
    )
    result = acceptance.run_acceptance(notifier=Sender())
    assert result["already_delivered"] is True
    assert result["messages_sent"] == 0
    assert checked == [expected_key]


def test_acceptance_allows_only_one_full_fidelity_attempt(monkeypatch):
    data = snapshot()
    sender = Sender()
    monkeypatch.setattr(acceptance.db, "get_persisted_daily_picks", lambda: data)
    monkeypatch.setattr(acceptance.db, "get_notification_delivery_status", lambda _key: None)
    monkeypatch.setattr(acceptance.db, "is_notification_delivered", lambda _key: False)
    records = []
    monkeypatch.setattr(acceptance.db, "record_notification_delivery", lambda *args: records.append(args))
    calls = []

    def send_once(dataset, **kwargs):
        calls.append(dataset["run_id"])
        kwargs["record_delivery"]("ignored", dataset["run_id"], "hash", 1, 1)
        return True

    monkeypatch.setattr(acceptance, "send_full_fidelity_daily", send_once)
    result = acceptance.run_acceptance(notifier=sender)
    assert result["delivery"] == "SUCCESS"
    assert result["messages_sent"] == 1
    assert calls == [data["run_id"]]
    assert len(records) == 1
    assert records[0][0] != "ignored"


def test_acceptance_rejects_multi_message_report(monkeypatch):
    monkeypatch.setattr(
        acceptance,
        "validate_notification_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("acceptance report requires 2 messages; expected exactly one")
        ),
    )
    with pytest.raises(ValueError, match="exactly one"):
        acceptance.validate_snapshot(snapshot())


def test_acceptance_does_not_retry_unresolved_attempt(monkeypatch):
    monkeypatch.setattr(acceptance.db, "get_persisted_daily_picks", snapshot)
    monkeypatch.setattr(acceptance.db, "get_notification_delivery_status", lambda _key: "PARTIAL")
    with pytest.raises(RuntimeError, match="manual review"):
        acceptance.run_acceptance(notifier=Sender())
