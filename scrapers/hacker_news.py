"""Show HN discovery through the official public Firebase API."""

from __future__ import annotations

from html import unescape
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import urllib.error
import urllib.request

from models import Product
from scrapers.base_scraper import BaseScraper, ScraperFetchError


class HackerNewsScraper(BaseScraper):
    """Fetch a bounded set of recent Show HN submissions."""

    API_ROOT = "https://hacker-news.firebaseio.com/v0"
    USER_AGENT = "ProductPicker/0.1 (official Hacker News API client)"
    REQUEST_TIMEOUT = 10
    MAX_ITEMS = 75

    @property
    def source_name(self) -> str:
        return "hacker_news"

    def fetch(self) -> list[Product]:
        ids = self._get_json(f"{self.API_ROOT}/showstories.json")
        if not isinstance(ids, list) or not ids:
            raise ScraperFetchError("Hacker News Show HN feed returned no item IDs")
        products: list[Product] = []
        failures = 0
        # Firebase exposes one item per endpoint. A small fixed worker pool keeps
        # the bounded public probe practical without broad concurrency.
        selected_ids = ids[: self.MAX_ITEMS]
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self._get_json, f"{self.API_ROOT}/item/{int(item_id)}.json"): item_id
                for item_id in selected_ids
            }
            for future in as_completed(futures):
                try:
                    products.append(self._parse_item(future.result()))
                except (ScraperFetchError, TypeError, ValueError, KeyError):
                    failures += 1
        if not products:
            raise ScraperFetchError(
                f"Hacker News returned no usable Show HN items ({failures} item failures)"
            )
        return products

    def _get_json(self, url: str):
        request = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.REQUEST_TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ScraperFetchError(
                f"Hacker News API failed; HTTP status: {exc.code}; reason: {exc.reason}"
            ) from exc
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            reason = getattr(exc, "reason", None) or str(exc)
            raise ScraperFetchError(
                f"Hacker News API failed; HTTP status: unavailable; reason: {reason}"
            ) from exc

    def _parse_item(self, item: dict) -> Product:
        item_id = str(item["id"])
        title = str(item["title"]).strip()
        if not title.casefold().startswith("show hn:"):
            raise ValueError("not a Show HN submission")
        hn_url = f"https://news.ycombinator.com/item?id={item_id}"
        external_url = str(item.get("url") or "").strip()
        raw_text = str(item.get("text") or "")
        description = re.sub(r"<[^>]+>", " ", unescape(raw_text))
        description = " ".join(description.split()) or re.sub(
            r"^show hn:\s*", "", title, flags=re.I
        )
        return Product(
            project_id=item_id,
            source_platform=self.source_name,
            url=hn_url,
            title=title,
            description=description,
            category="Show HN",
            image_url=external_url or hn_url,
            raw_data={
                "hn_item_id": int(item_id),
                "points": item.get("score"),
                "comment_count": item.get("descendants"),
                "submitted_at": item.get("time"),
                "author": item.get("by"),
                "hn_url": hn_url,
                "external_product_url": external_url or None,
                "user_feedback_available": False,
            },
        )
