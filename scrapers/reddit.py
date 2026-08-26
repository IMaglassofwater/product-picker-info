"""Reddit RSS scraper for product discovery subreddits."""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from models import Product
from scrapers.base_scraper import BaseScraper, ScraperFetchError


class _ContentParser(HTMLParser):
    """Extract readable text and the first image URL from entry HTML."""

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
        attributes = dict(attrs)
        source = attributes.get("src")
        if source and source.startswith(("http://", "https://")):
            self.image_url = source

    @property
    def text(self) -> str:
        """Return normalized plain text extracted from HTML."""
        return " ".join(self.text_parts)


class RedditScraper(BaseScraper):
    """Fetch public RSS feeds from selected product discovery subreddits."""

    SUBREDDITS = ("EDC", "ShutUpAndTakeMyMoney")
    USER_AGENT = "ProductPicker/0.1 (public RSS reader)"
    REQUEST_TIMEOUT = 10
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 1.0

    @property
    def source_name(self) -> str:
        """Return the stable platform identifier."""
        return "reddit"

    def fetch(self) -> list[Product]:
        """Fetch and normalize posts from configured public Reddit RSS feeds.

        A network or feed-level XML failure raises :class:`ScraperFetchError`.
        An invalid individual entry is skipped so other entries remain usable.
        """
        products: list[Product] = []
        for subreddit in self.SUBREDDITS:
            feed_url = f"https://www.reddit.com/r/{subreddit}/.rss"
            feed_data = self._fetch_feed(feed_url)
            try:
                root = ET.fromstring(feed_data)
            except ET.ParseError as exc:
                raise ScraperFetchError(
                    f"Invalid Reddit RSS for r/{subreddit}"
                ) from exc

            for entry in self._entries(root):
                try:
                    products.append(self._parse_entry(entry, subreddit))
                except (KeyError, TypeError, ValueError):
                    continue
        return products

    def _fetch_feed(self, feed_url: str) -> bytes:
        """Download one public RSS feed with bounded retries."""
        request = urllib.request.Request(
            feed_url,
            headers={"User-Agent": self.USER_AGENT},
        )
        last_error: OSError | urllib.error.URLError | None = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(
                    request, timeout=self.REQUEST_TIMEOUT
                ) as response:
                    return response.read()
            except (OSError, urllib.error.URLError) as exc:
                last_error = exc
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY_SECONDS)

        status = (
            str(last_error.code)
            if isinstance(last_error, urllib.error.HTTPError)
            else "unavailable"
        )
        reason = getattr(last_error, "reason", None) or str(last_error)
        raise ScraperFetchError(
            "Reddit RSS request failed after "
            f"{self.MAX_RETRIES} attempts; HTTP status: {status}; "
            f"reason: {reason}; URL: {feed_url}"
        ) from last_error

    @staticmethod
    def _entries(root: ET.Element) -> list[ET.Element]:
        """Return Atom entries or RSS items without relying on namespaces."""
        return [
            element
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1] in {"entry", "item"}
        ]

    def _parse_entry(self, entry: ET.Element, subreddit: str) -> Product:
        """Convert one RSS/Atom entry to the shared Product model."""
        title = self._text(entry, "title")
        entry_id = self._text(entry, "id", required=False)
        content = self._text(entry, "content", required=False) or self._text(
            entry, "description", required=False
        )
        url = self._link(entry)
        project_id = self._project_id(entry_id, url)

        content_parser = _ContentParser()
        content_parser.feed(content)
        image_url = content_parser.image_url

        product = Product(
            project_id=project_id,
            source_platform=self.source_name,
            url=url,
            title=title,
            description=content_parser.text or title,
            category=subreddit,
            image_url=image_url or url,
            raw_data={
                "id": entry_id,
                "title": title,
                "url": url,
                "content": content,
                "subreddit": subreddit,
            },
        )
        if not image_url:
            # Product currently validates non-empty image URLs during creation;
            # RSS semantics require the normalized value to be empty when absent.
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
            raise ValueError(f"Missing RSS field: {local_name}")
        return ""

    @staticmethod
    def _link(entry: ET.Element) -> str:
        for child in entry:
            if child.tag.rsplit("}", 1)[-1] != "link":
                continue
            url = (child.get("href") or child.text or "").strip()
            if url.startswith(("http://", "https://")):
                return url
        raise ValueError("Missing valid RSS link")

    @staticmethod
    def _project_id(entry_id: str, url: str) -> str:
        if entry_id:
            return entry_id.removeprefix("t3_")
        match = re.search(r"/comments/([^/]+)", url)
        if match:
            return match.group(1)
        raise ValueError("Missing Reddit post id")
