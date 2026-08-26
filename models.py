"""Core product data models."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from typing import Any
from urllib.parse import urlparse


@dataclass
class Product:
    """A product discovered on an external source platform."""

    project_id: str
    source_platform: str
    url: str
    title: str
    description: str
    category: str
    image_url: str
    raw_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Legacy source records may legitimately have no body text.  Keep the
        # record visible and normalize a database NULL instead of discarding it.
        if self.description is None:
            self.description = ""
        string_fields = (
            "project_id", "source_platform", "url", "title", "category",
            "image_url",
        )
        for field_name in string_fields:
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

        if not isinstance(self.description, str):
            raise ValueError("description must be a string")

        for field_name in ("url", "image_url"):
            parsed_url = urlparse(getattr(self, field_name))
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                raise ValueError(f"{field_name} must be a valid HTTP(S) URL")

        if not isinstance(self.raw_data, dict):
            raise ValueError("raw_data must be a dictionary")


@dataclass(frozen=True)
class AITriageResult:
    candidate_id: str
    triage_status: Literal["PASS", "REVIEW", "REJECT"]
    triage_score: int
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    primary_reason: str
    opportunity_type: Literal["product_improvement", "unmet_demand", "design_inspiration", "consumer_trend", "unknown"]
    key_opportunity: str
    main_risks: list[str]
    needs_deep_analysis: bool
    provider: str
    model: str
    display_title_zh: str | None = None
    primary_reason_zh: str | None = None
    key_opportunity_zh: str | None = None
    main_risks_zh: list[str] = field(default_factory=list)
    analyzed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if self.triage_status not in {"PASS", "REVIEW", "REJECT"} or not 1 <= self.triage_score <= 10:
            raise ValueError("invalid triage status or score")
        ranges = {"PASS": range(8, 11), "REVIEW": range(5, 8), "REJECT": range(1, 5)}
        if self.triage_score not in ranges[self.triage_status]:
            raise ValueError("triage status and score disagree")
        if len(self.primary_reason) > 120 or len(self.key_opportunity) > 160 or len(self.main_risks) > 3 or any(len(x) > 80 for x in self.main_risks):
            raise ValueError("triage output exceeds limits")
