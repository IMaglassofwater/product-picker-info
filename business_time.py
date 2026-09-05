"""Timezone-aware Product Picker business-date helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


PRODUCT_PICKER_TIMEZONE = ZoneInfo("Asia/Shanghai")


def product_picker_business_date(value: datetime | None = None) -> date:
    """Return the Product Picker calendar date in Asia/Shanghai."""
    moment = value or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(PRODUCT_PICKER_TIMEZONE).date()
