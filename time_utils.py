"""UTC persistence and Asia/Tokyo business-time helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


TOKYO = ZoneInfo("Asia/Tokyo")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_tokyo(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TOKYO)


def format_tokyo(value: datetime, fmt: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    return to_tokyo(value).strftime(fmt)
