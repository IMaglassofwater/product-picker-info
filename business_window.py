"""Asia/Shanghai business-window and trustworthy source-time semantics."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
SOURCE_TIME_KEYS = (
    "published_at", "published", "datePublished", "date_published",
    "created_at", "created_utc", "campaignStartDate", "campaign_start_date",
)


def daily_window(business_date: date | str | None = None) -> tuple[datetime, datetime, date]:
    """Return [previous noon, current noon) for the Shanghai delivery date."""
    selected = date.fromisoformat(business_date) if isinstance(business_date, str) else business_date
    selected = selected or datetime.now(SHANGHAI).date()
    end = datetime.combine(selected, time(12), tzinfo=SHANGHAI)
    return end - timedelta(days=1), end, selected


def parse_timestamp(value) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), timezone.utc).astimezone(SHANGHAI)
        except (OSError, OverflowError, ValueError):
            return None
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(SHANGHAI)
    except (TypeError, ValueError):
        return None


def effective_evidence_timestamp(record: dict) -> tuple[datetime | None, str]:
    """Prefer source-native publication time; fall back honestly to observation time."""
    raw = record.get("raw_data") if isinstance(record.get("raw_data"), dict) else {}
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    for key in SOURCE_TIME_KEYS:
        parsed = parse_timestamp(raw.get(key, metadata.get(key)))
        if parsed is not None:
            return parsed, f"source:{key}"
    return parse_timestamp(record.get("observation_timestamp")), "observation"


def record_in_window(record: dict, start: datetime, end: datetime) -> bool:
    timestamp, _method = effective_evidence_timestamp(record)
    return timestamp is not None and start <= timestamp < end
