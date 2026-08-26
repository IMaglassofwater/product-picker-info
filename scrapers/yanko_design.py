"""Yanko Design scraper using the public RSS feed only."""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import urllib.error
import urllib.request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from models import Product
from scrapers.base_scraper import BaseScraper, ScraperFetchError


class _RSSContentParser(HTMLParser):
    """Extract readable text and the first public image from RSS HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self.image_url = ""

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.text_parts.append(text)

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.lower() != "img" or self.image_url:
            return
        source = dict(attrs).get("src") or ""
        if source.startswith(("http://", "https://")):
            self.image_url = source

    @property
    def text(self) -> str:
        return " ".join(self.text_parts)


class YankoDesignScraper(BaseScraper):
    """Normalize at most 50 recent Yanko Design RSS entries as Products."""

    FEED_URL = "https://www.yankodesign.com/feed/"
    USER_AGENT = "ProductPicker/0.1 (public RSS reader)"
    REQUEST_TIMEOUT = 15
    MAX_ITEMS = 50

    @property
    def source_name(self) -> str:
        return "yanko_design"

    def fetch(self) -> list[Product]:
        """Fetch and parse the public RSS feed without opening article pages."""
        payload = self._fetch_feed()
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise ScraperFetchError(f"Yanko Design RSS parsing failed: {exc}") from exc

        entries = root.findall("./channel/item")[: self.MAX_ITEMS]
        if not entries:
            raise ScraperFetchError("Yanko Design RSS returned no entries")

        products: list[Product] = []
        for entry in entries:
            try:
                products.append(self._parse_entry(entry))
            except (TypeError, ValueError):
                continue
        if not products:
            raise ScraperFetchError(
                "Yanko Design RSS contained no valid product entries"
            )
        return products

    def _fetch_feed(self) -> bytes:
        request = urllib.request.Request(
            self.FEED_URL,
            headers={"User-Agent": self.USER_AGENT},
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.REQUEST_TIMEOUT
            ) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise ScraperFetchError(
                f"Yanko Design RSS request failed; HTTP status: {exc.code}; "
                f"reason: {exc.reason}"
            ) from exc
        except (OSError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", None) or str(exc)
            raise ScraperFetchError(
                "Yanko Design RSS request failed; HTTP status: unavailable; "
                f"reason: {reason}"
            ) from exc

    def _parse_entry(self, entry: ET.Element) -> Product:
        title = self._text(entry, "title")
        url = self._canonical_url(self._text(entry, "link"))
        if not url.startswith(("http://", "https://")):
            raise ValueError("Missing valid Yanko Design article URL")

        raw_description = self._text(entry, "description", required=False)
        encoded_content = self._text(entry, "encoded", required=False)
        parser = _RSSContentParser()
        parser.feed(raw_description or encoded_content)
        media_parser = _RSSContentParser()
        media_parser.feed(f"{raw_description} {encoded_content}")
        description = parser.text.strip()
        if description.casefold().startswith(title.casefold()):
            description = description[len(title) :].strip()
        description = description or title

        categories = self._categories(entry)
        published_at = self._text(entry, "pubDate", required=False)
        guid = self._text(entry, "guid", required=False)
        image_url = self._image_url(entry) or media_parser.image_url
        project_id = guid or hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]

        product = Product(
            project_id=project_id,
            source_platform=self.source_name,
            url=url,
            title=title,
            description=description,
            category=categories[0] if categories else "uncategorized",
            image_url=image_url or url,
            raw_data={
                "categories": categories,
                "tags": categories,
                "image_url": image_url,
                "published_at": published_at,
                "rss_guid": guid,
            },
        )
        if not image_url:
            product.image_url = ""
        return product

    @staticmethod
    def _text(
        entry: ET.Element, local_name: str, *, required: bool = True
    ) -> str:
        for child in entry:
            if child.tag.rsplit("}", 1)[-1] == local_name:
                value = "".join(child.itertext()).strip()
                if value or not required:
                    return value
        if required:
            raise ValueError(f"Missing Yanko Design RSS field: {local_name}")
        return ""

    @staticmethod
    def _categories(entry: ET.Element) -> list[str]:
        categories: list[str] = []
        seen: set[str] = set()
        for child in entry:
            if child.tag.rsplit("}", 1)[-1] != "category":
                continue
            value = "".join(child.itertext()).strip()
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                categories.append(value)
        return categories

    @staticmethod
    def _image_url(entry: ET.Element) -> str:
        for child in entry:
            local_name = child.tag.rsplit("}", 1)[-1]
            candidate = (child.get("url") or "").strip()
            if (
                local_name in {"content", "thumbnail", "enclosure"}
                and candidate.startswith(("http://", "https://"))
                and (
                    local_name != "enclosure"
                    or (child.get("type") or "").startswith("image/")
                )
            ):
                return candidate
        return ""

    @staticmethod
    def _canonical_url(url: str) -> str:
        parts = urlsplit(url.strip())
        query = urlencode(
            [
                (key, value)
                for key, value in parse_qsl(parts.query, keep_blank_values=True)
                if not key.casefold().startswith("utm_")
            ]
        )
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
