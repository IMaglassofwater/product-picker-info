"""Historical Reddit adapter for the third-party Arctic Shift API.

Arctic Shift is not Reddit's official API. Its data is not guaranteed to be
real-time, and the service provides no uptime guarantee.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

from config import (
    REDDIT_INTENTS,
    REDDIT_INTENT_QUERY_BATCHES,
    REDDIT_LIMIT_PER_SUBREDDIT,
    REDDIT_LOOKBACK_DAYS,
    REDDIT_SUBREDDITS,
    REDDIT_SUBREDDIT_INTENTS,
)
from models import Product
from scrapers.base_scraper import BaseScraper, ScraperFetchError


class ArcticShiftScraper(BaseScraper):
    """Read recent historical posts from selected subreddits via Arctic Shift."""

    BASE_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
    USER_AGENT = "ProductPicker/0.1 (Arctic Shift historical reader)"
    REQUEST_TIMEOUT = 15

    def __init__(
        self,
        subreddits: Iterable[str] | None = None,
        limit_per_subreddit: int = REDDIT_LIMIT_PER_SUBREDDIT,
    ) -> None:
        configured = tuple(item["name"] for item in REDDIT_SUBREDDITS)
        self.subreddits = tuple(subreddits) if subreddits is not None else configured
        self.community_weights = {
            item["name"].lower(): item["weight"] for item in REDDIT_SUBREDDITS
        }
        self.limit_per_subreddit = max(1, min(100, limit_per_subreddit))
        self.fetch_counts: dict[str, int] = {}
        self.raw_fetch_counts: dict[str, int] = {}
        self.invalid_counts: dict[str, int] = {}
        self.failures: dict[str, str] = {}
        self.query_failures: dict[str, list[str]] = {}

    @property
    def source_name(self) -> str:
        return "reddit_arctic_shift"

    def fetch(self) -> list[Product]:
        """Fetch a bounded set of historical posts from each subreddit."""
        products: list[Product] = []
        seen_urls: set[str] = set()
        self.fetch_counts = {}
        self.raw_fetch_counts = {}
        self.invalid_counts = {}
        self.failures = {}
        self.query_failures = {}
        for subreddit in self.subreddits:
            self.fetch_counts[subreddit] = 0
            self.raw_fetch_counts[subreddit] = 0
            self.invalid_counts[subreddit] = 0
            successful_queries = 0
            for query in self._intent_batches(subreddit):
                try:
                    records = self._fetch_subreddit(subreddit, query)
                    successful_queries += 1
                except ScraperFetchError as exc:
                    self.query_failures.setdefault(subreddit, []).append(str(exc))
                    continue
                self.raw_fetch_counts[subreddit] += len(records)
                for record in records:
                    if self.fetch_counts[subreddit] >= self.limit_per_subreddit:
                        break
                    if not self._has_valid_text(record):
                        self.invalid_counts[subreddit] += 1
                        continue
                    try:
                        product = self._parse_post(record, subreddit)
                    except (KeyError, TypeError, ValueError):
                        self.invalid_counts[subreddit] += 1
                        continue
                    if not product.raw_data["matched_intents"]:
                        self.invalid_counts[subreddit] += 1
                        continue
                    if product.url in seen_urls:
                        continue
                    seen_urls.add(product.url)
                    products.append(product)
                    self.fetch_counts[subreddit] += 1
            if successful_queries == 0:
                self.failures[subreddit] = "; ".join(
                    self.query_failures.get(subreddit, [])
                )
        if not products:
            details = "; ".join(
                f"{name}: {reason}" for name, reason in self.failures.items()
            )
            message = "Arctic Shift returned no valid posts"
            raise ScraperFetchError(f"{message}; {details}" if details else message)
        return products

    def _fetch_subreddit(
        self, subreddit: str, query_text: str | None = None
    ) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode(
            {
                "subreddit": subreddit,
                "limit": self.limit_per_subreddit,
                "sort": "desc",
                **({"query": query_text} if query_text else {}),
                "after": (
                    datetime.now(timezone.utc) - timedelta(days=REDDIT_LOOKBACK_DAYS)
                ).date().isoformat(),
                "fields": (
                    "id,title,selftext,subreddit,url,score,"
                    "num_comments,created_utc,author"
                ),
            }
        )
        request = urllib.request.Request(
            f"{self.BASE_URL}?{query}",
            headers={"User-Agent": self.USER_AGENT},
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.REQUEST_TIMEOUT
            ) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            raise ScraperFetchError(
                "Arctic Shift request failed; "
                f"HTTP status: {exc.code}; reason: {exc.reason}"
            ) from exc
        except (OSError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", None) or str(exc)
            raise ScraperFetchError(
                "Arctic Shift request failed; HTTP status: unavailable; "
                f"reason: {reason}"
            ) from exc

        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ScraperFetchError(f"Arctic Shift JSON parsing failed: {exc}") from exc
        records = decoded.get("data") if isinstance(decoded, dict) else decoded
        if not isinstance(records, list):
            raise ScraperFetchError("Arctic Shift response has an invalid structure")
        return [record for record in records if isinstance(record, dict)]

    def _intent_batches(self, subreddit: str) -> tuple[str, str]:
        """Return two representative queries; Arctic post OR search is unstable."""
        return REDDIT_INTENT_QUERY_BATCHES.get(
            subreddit.lower(), ("recommend", "need")
        )

    def _parse_post(self, record: dict[str, Any], subreddit: str) -> Product:
        post_id = self._required(record, "id")
        title = self._required(record, "title")
        post_subreddit = str(record.get("subreddit") or subreddit).strip()
        selftext = str(record.get("selftext") or "").strip()
        url = self._post_url(record)

        product = Product(
            project_id=post_id.removeprefix("t3_"),
            source_platform=self.source_name,
            url=url,
            title=title,
            description=selftext or title,
            category=post_subreddit,
            image_url=url,
            raw_data={
                "score": self._integer(record.get("score")),
                "num_comments": self._integer(record.get("num_comments")),
                "created_utc": record.get("created_utc"),
                "author": record.get("author"),
                "subreddit": post_subreddit,
                "community_weight": self.community_weights.get(
                    post_subreddit.lower(), "unspecified"
                ),
                "matched_intents": self._matched_intents(
                    title, selftext, post_subreddit
                ),
                "intent_source": self._intent_source(
                    title, selftext, post_subreddit
                ),
                "retrieval_source": "arctic_shift",
            },
        )
        if not selftext:
            product.description = ""
        product.image_url = ""
        return product

    @staticmethod
    def _has_valid_text(record: dict[str, Any]) -> bool:
        title = str(record.get("title") or "").strip()
        selftext = str(record.get("selftext") or "").strip()
        invalid_markers = {"[removed]", "[deleted]", "removed", "deleted"}
        if title.lower() in invalid_markers or selftext.lower() in invalid_markers:
            return False
        if not title and not selftext:
            return False
        url = str(record.get("url") or "").lower().split("?", 1)[0]
        pure_image = record.get("post_hint") == "image" or url.endswith(
            (".jpg", ".jpeg", ".png", ".gif", ".webp")
        )
        return not (pure_image and not selftext and len(title) < 20)

    @staticmethod
    def _matched_intents(title: str, selftext: str, subreddit: str) -> list[str]:
        text = f"{title} {selftext}".casefold()
        configured = (
            *REDDIT_INTENTS,
            *REDDIT_SUBREDDIT_INTENTS.get(subreddit.lower(), ()),
        )
        return [intent for intent in dict.fromkeys(configured) if intent.casefold() in text]

    @staticmethod
    def _intent_source(title: str, selftext: str, subreddit: str) -> str:
        text = f"{title} {selftext}".casefold()
        specific = REDDIT_SUBREDDIT_INTENTS.get(subreddit.lower(), ())
        if any(intent.casefold() in text for intent in specific):
            return subreddit
        return "general"

    @staticmethod
    def _post_url(record: dict[str, Any]) -> str:
        permalink = record.get("permalink")
        if isinstance(permalink, str) and permalink.strip():
            permalink = permalink.strip()
            if permalink.startswith("/"):
                return "https://www.reddit.com" + permalink
            if permalink.startswith(("http://", "https://")):
                return permalink
        url = record.get("url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return url
        raise ValueError("Missing Arctic Shift post URL")

    @staticmethod
    def _required(record: dict[str, Any], key: str) -> str:
        value = record.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing Arctic Shift field: {key}")
        return value.strip()

    @staticmethod
    def _integer(value: Any) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
