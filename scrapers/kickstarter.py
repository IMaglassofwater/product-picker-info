"""Kickstarter adapter backed by the public KSInsights CSV dataset."""

from __future__ import annotations

import csv
import io
import json
import urllib.error
import urllib.request
from typing import Any

from models import Product
from scrapers.base_scraper import BaseScraper, ScraperFetchError


class KickstarterScraper(BaseScraper):
    """Read Kickstarter Technology and Design data published by KSInsights.

    Direct Kickstarter page access is intentionally not used because that
    route is currently blocked. This adapter reads the third-party KSInsights
    repository's public structured dataset without cloning the repository.
    """

    DAILY_INDEX_URL = (
        "https://api.github.com/repos/ImWhiteRabbit/KSInsights/contents/"
        "data/daily?ref=main"
    )
    USER_AGENT = "ProductPicker/0.1 (KSInsights public dataset reader)"
    REQUEST_TIMEOUT = 20

    @property
    def source_name(self) -> str:
        return "kickstarter"

    def fetch(self) -> list[Product]:
        """Load the latest public KSInsights daily CSV as Products."""
        daily_entries = self._fetch_json(self.DAILY_INDEX_URL)
        daily_directory_url = self._latest_daily_directory(daily_entries)
        dataset_entries = self._fetch_json(daily_directory_url)
        dataset_url = self._csv_download_url(dataset_entries)
        records = self._parse_csv(self._fetch_bytes(dataset_url))

        products: list[Product] = []
        for record in records:
            try:
                products.append(self._parse_project(record))
            except (KeyError, TypeError, ValueError):
                continue
        if not products:
            raise ScraperFetchError("KSInsights dataset contained no valid projects")
        return products

    def _fetch_json(self, url: str) -> Any:
        payload = self._fetch_bytes(url)
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ScraperFetchError(f"KSInsights JSON parsing failed: {exc}") from exc

    def _fetch_bytes(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": "application/vnd.github+json",
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.REQUEST_TIMEOUT
            ) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise ScraperFetchError(
                "KSInsights request failed; "
                f"HTTP status: {exc.code}; reason: {exc.reason}"
            ) from exc
        except (OSError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", None) or str(exc)
            raise ScraperFetchError(
                "KSInsights request failed; HTTP status: unavailable; "
                f"reason: {reason}"
            ) from exc

    @staticmethod
    def _latest_daily_directory(entries: Any) -> str:
        if not isinstance(entries, list):
            raise ScraperFetchError("KSInsights daily index has an invalid structure")
        directories = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("type") == "dir"
            and str(entry.get("name", "")).isdigit()
            and isinstance(entry.get("url"), str)
        ]
        if not directories:
            raise ScraperFetchError("KSInsights daily index contained no datasets")
        return max(directories, key=lambda entry: entry["name"])["url"]

    @staticmethod
    def _csv_download_url(entries: Any) -> str:
        if not isinstance(entries, list):
            raise ScraperFetchError("KSInsights dataset index has an invalid structure")
        csv_files = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and str(entry.get("name", "")).lower().endswith(".csv")
            and isinstance(entry.get("download_url"), str)
        ]
        if not csv_files:
            raise ScraperFetchError("KSInsights dataset index contained no CSV file")
        return sorted(csv_files, key=lambda entry: entry["name"])[-1]["download_url"]

    @staticmethod
    def _parse_csv(payload: bytes) -> list[dict[str, str]]:
        try:
            text = payload.decode("utf-8-sig")
            rows = list(csv.DictReader(io.StringIO(text)))
        except (UnicodeDecodeError, csv.Error) as exc:
            raise ScraperFetchError(f"KSInsights CSV parsing failed: {exc}") from exc
        if not rows:
            raise ScraperFetchError("KSInsights CSV dataset was empty")
        return rows

    def _parse_project(self, record: dict[str, str]) -> Product:
        project_id = self._required(record, "id")
        url = self._required(record, "project_url")
        title = self._required(record, "name")
        description = self._required(record, "blurb")
        if not url.startswith(("http://", "https://")):
            raise ValueError("Invalid KSInsights project_url")

        category_name = self._optional(record, "category_name")
        category_parent_name = self._optional(record, "category_parent_name")
        category = category_name or category_parent_name or "uncategorized"

        product = Product(
            project_id=project_id,
            source_platform=self.source_name,
            url=url,
            title=title,
            description=description,
            category=category,
            image_url=url,
            raw_data={
                "backers_count": self._integer(record.get("backers_count")),
                "goal": self._number(record.get("goal")),
                "pledged": self._number(record.get("pledged")),
                "percent_funded": self._number(record.get("percent_funded")),
                "currency": self._optional(record, "currency") or None,
                "state": self._optional(record, "state") or None,
                "deadline": self._optional(record, "deadline") or None,
                "launched_at": self._optional(record, "launched_at") or None,
                "creator_name": self._optional(record, "creator_name") or None,
                "country": self._optional(record, "country") or None,
                "category_name": category_name or None,
                "category_parent_name": category_parent_name or None,
                "data_source": "KSInsights",
            },
        )
        product.image_url = ""
        return product

    @staticmethod
    def _required(record: dict[str, str], key: str) -> str:
        value = KickstarterScraper._optional(record, key)
        if not value:
            raise ValueError(f"Missing KSInsights field: {key}")
        return value

    @staticmethod
    def _optional(record: dict[str, str], key: str) -> str:
        value = record.get(key)
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            normalized = str(value).strip().replace(",", "").rstrip("%")
            return float(normalized) if normalized else None
        except ValueError:
            return None

    @classmethod
    def _integer(cls, value: Any) -> int | None:
        number = cls._number(value)
        return int(number) if number is not None else None
