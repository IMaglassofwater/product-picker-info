"""Indiegogo scraper using the documented public active-projects endpoint."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from models import Product
from scrapers.base_scraper import BaseScraper, ScraperFetchError


class IndiegogoScraper(BaseScraper):
    """Normalize public active crowdfunding projects without authentication."""

    ENDPOINT = "https://www.indiegogo.com/api/public/projects/getActiveCrowdfundingProjects"
    USER_AGENT = "ProductPicker/0.1 (Indiegogo official public API reader)"
    REQUEST_TIMEOUT = 20
    MAX_ITEMS = 100

    @property
    def source_name(self) -> str:
        return "indiegogo"

    def fetch(self) -> list[Product]:
        try:
            payload = json.loads(self._fetch_bytes().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ScraperFetchError(f"Indiegogo public API parsing failed: {exc}") from exc
        records = payload if isinstance(payload, list) else payload.get("projects", []) if isinstance(payload, dict) else []
        if not records:
            raise ScraperFetchError("Indiegogo public API returned no projects")
        products = []
        for record in records[: self.MAX_ITEMS]:
            try:
                products.append(self._parse_project(record))
            except (TypeError, ValueError):
                continue
        if not products:
            raise ScraperFetchError("Indiegogo public API contained no valid projects")
        return products

    def _fetch_bytes(self) -> bytes:
        request = urllib.request.Request(
            self.ENDPOINT,
            headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.REQUEST_TIMEOUT) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise ScraperFetchError(
                f"Indiegogo request failed; HTTP status: {exc.code}; reason: {exc.reason}"
            ) from exc
        except (OSError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", None) or str(exc)
            raise ScraperFetchError(
                f"Indiegogo request failed; HTTP status: unavailable; reason: {reason}"
            ) from exc

    @staticmethod
    def _number(record: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = record.get(key)
            if value is None or isinstance(value, bool):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def _parse_project(self, record: dict[str, Any]) -> Product:
        if not isinstance(record, dict):
            raise ValueError("Invalid Indiegogo project")
        title = str(record.get("projectName") or "").strip()
        description = str(record.get("shortDescription") or title).strip()
        url = str(record.get("projectHomeUrl") or "").strip()
        image = str(record.get("projectImageUrl") or url).strip()
        if not title or not url.startswith(("http://", "https://")):
            raise ValueError("Missing Indiegogo title or URL")
        goal = self._number(record, "campaignGoal")
        gathered = self._number(record, "fundsGathered")
        percentage = round(gathered / goal * 100, 2) if goal and goal > 0 and gathered is not None else None
        source_id = str(
            record.get("projectId") or record.get("id") or record.get("projectSlug") or url
        )
        raw_data = {
            "source_id": source_id,
            "campaign_goal": goal,
            "funds_gathered": gathered,
            "funding_percentage": percentage,
            "currency": record.get("currencyShortName"),
            "backer_count": self._number(record, "backerCount"),
            "campaign_start_date": record.get("campaignStartDate"),
            "campaign_end_date": record.get("campaignEndDate"),
            "creator_name": record.get("creatorName"),
            "comment_count": self._number(record, "commentCount"),
            "campaign_status": record.get("campaignStatus") or record.get("status"),
            "fetched_at": _now_iso(),
        }
        product = Product(
            project_id=source_id,
            source_platform=self.source_name,
            url=url,
            title=title,
            description=description or title,
            category=str(record.get("categoryName") or record.get("category") or "uncategorized"),
            image_url=image if image.startswith(("http://", "https://")) else url,
            raw_data=raw_data,
        )
        if not record.get("projectImageUrl"):
            product.image_url = ""
        return product


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
