"""Design Milk discovery using its public RSS feed."""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from models import Product
from scrapers.base_scraper import BaseScraper, ScraperFetchError


class _ContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.image_url = ""

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "img" and not self.image_url:
            value = dict(attrs).get("src") or ""
            if value.startswith(("http://", "https://")):
                self.image_url = value


class DesignMilkScraper(BaseScraper):
    """Normalize up to 30 Design Milk public feed entries."""

    FEED_URL = "https://feeds.feedburner.com/design-milk"
    USER_AGENT = "ProductPicker/0.1 (public RSS reader)"
    REQUEST_TIMEOUT = 15
    MAX_ITEMS = 30
    ACCESS_STATUS = "DEFERRED"

    def __init__(self, *, access_enabled: bool = False) -> None:
        self.access_enabled = access_enabled

    @property
    def source_name(self) -> str:
        return "design_milk"

    def fetch(self) -> list[Product]:
        if not self.access_enabled:
            raise ScraperFetchError(
                "Design Milk source is DEFERRED after bounded public access probe"
            )
        request = urllib.request.Request(self.FEED_URL, headers={"User-Agent": self.USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.REQUEST_TIMEOUT) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            raise ScraperFetchError(
                f"Design Milk RSS failed; HTTP status: {exc.code}; reason: {exc.reason}"
            ) from exc
        except (OSError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", None) or str(exc)
            raise ScraperFetchError(
                f"Design Milk RSS failed; HTTP status: unavailable; reason: {reason}"
            ) from exc
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise ScraperFetchError(f"Design Milk RSS parsing failed: {exc}") from exc
        entries = root.findall("./channel/item")[: self.MAX_ITEMS]
        if not entries:
            raise ScraperFetchError("Design Milk RSS returned no entries")
        products: list[Product] = []
        for entry in entries:
            try:
                products.append(self._parse_entry(entry))
            except (TypeError, ValueError):
                continue
        if not products:
            raise ScraperFetchError("Design Milk RSS contained no usable entries")
        return products

    def _parse_entry(self, entry: ET.Element) -> Product:
        title = self._text(entry, "title")
        url = self._text(entry, "link")
        if not url.startswith(("http://", "https://")):
            raise ValueError("invalid Design Milk URL")
        description_html = self._text(entry, "description", required=False)
        content_html = self._text(entry, "encoded", required=False)
        parser = _ContentParser()
        parser.feed(f"{description_html} {content_html}")
        categories = self._categories(entry)
        published = self._text(entry, "pubDate", required=False)
        guid = self._text(entry, "guid", required=False)
        return Product(
            project_id=guid or hashlib.sha256(url.encode()).hexdigest()[:24],
            source_platform=self.source_name,
            url=url,
            title=title,
            description=" ".join(parser.parts) or title,
            category=categories[0] if categories else "uncategorized",
            image_url=parser.image_url or url,
            raw_data={
                "categories": categories,
                "tags": categories,
                "published_at": published,
                "rss_guid": guid,
                "image_url": parser.image_url,
                "user_feedback_available": False,
            },
        )

    @staticmethod
    def _text(entry: ET.Element, name: str, *, required: bool = True) -> str:
        for child in entry:
            if child.tag.rsplit("}", 1)[-1] == name:
                value = "".join(child.itertext()).strip()
                if value or not required:
                    return value
        if required:
            raise ValueError(f"missing Design Milk field: {name}")
        return ""

    @staticmethod
    def _categories(entry: ET.Element) -> list[str]:
        return list(dict.fromkeys(
            "".join(child.itertext()).strip()
            for child in entry
            if child.tag.rsplit("}", 1)[-1] == "category" and "".join(child.itertext()).strip()
        ))
