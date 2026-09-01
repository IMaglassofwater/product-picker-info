"""Etsy discovery through the official Open API only."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from models import Product
from scrapers.base_scraper import BaseScraper, ScraperFetchError


class EtsyScraper(BaseScraper):
    """Fetch a bounded, diverse sample of active Etsy listings."""

    API_URL = "https://openapi.etsy.com/v3/application/listings/active"
    USER_AGENT = "ProductPicker/0.1 (official Etsy Open API client)"
    REQUEST_TIMEOUT = 15
    RESULTS_PER_QUERY = 8
    DISCOVERY_QUERIES = (
        "home organization",
        "desk accessories",
        "travel accessories",
        "pet accessories",
        "kitchen accessories",
        "personalized stationery",
    )
    APPROVAL_STATUS = "DEFERRED_PENDING_PERSONAL_APPROVAL"

    def __init__(self, *, personal_approval_granted: bool | None = None) -> None:
        if personal_approval_granted is None:
            personal_approval_granted = os.getenv(
                "ETSY_PERSONAL_APPROVAL_GRANTED", "false"
            ).strip().casefold() in {"1", "true", "yes"}
        self.personal_approval_granted = personal_approval_granted

    @property
    def source_name(self) -> str:
        return "etsy"

    def fetch(self) -> list[Product]:
        """Return official active listings; fail clearly when access is absent."""
        if not self.personal_approval_granted:
            raise ScraperFetchError(self.APPROVAL_STATUS)
        key = os.getenv("ETSY_API_KEY", "").strip()
        secret = os.getenv("ETSY_SHARED_SECRET", "").strip()
        if not key or not secret:
            raise ScraperFetchError(
                "Etsy official API unavailable: ETSY_API_KEY and "
                "ETSY_SHARED_SECRET must be configured"
            )

        products: list[Product] = []
        seen: set[str] = set()
        failures: list[str] = []
        for query in self.DISCOVERY_QUERIES:
            try:
                payload = self._request_query(query, f"{key}:{secret}")
            except ScraperFetchError as exc:
                failures.append(str(exc))
                continue
            for listing in payload.get("results", []):
                try:
                    product = self._parse_listing(listing, query)
                except (KeyError, TypeError, ValueError):
                    continue
                if product.project_id in seen:
                    continue
                seen.add(product.project_id)
                products.append(product)
        if not products:
            detail = failures[0] if failures else "API returned no active listings"
            raise ScraperFetchError(f"Etsy official API returned no usable data: {detail}")
        return products

    def _request_query(self, query: str, api_key: str) -> dict[str, Any]:
        url = f"{self.API_URL}?{urllib.parse.urlencode({'keywords': query, 'limit': self.RESULTS_PER_QUERY, 'sort_on': 'created', 'sort_order': 'down'})}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self.USER_AGENT, "x-api-key": api_key},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.REQUEST_TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ScraperFetchError(
                f"Etsy API request failed; HTTP status: {exc.code}; reason: {exc.reason}"
            ) from exc
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            reason = getattr(exc, "reason", None) or str(exc)
            raise ScraperFetchError(
                f"Etsy API request failed; HTTP status: unavailable; reason: {reason}"
            ) from exc

    def _parse_listing(self, listing: dict[str, Any], query: str) -> Product:
        listing_id = str(listing["listing_id"])
        title = str(listing["title"]).strip()
        url = str(listing["url"]).strip()
        if not title or not url.startswith(("http://", "https://")):
            raise ValueError("invalid Etsy listing")
        price_data = listing.get("price") or {}
        amount = price_data.get("amount")
        divisor = price_data.get("divisor") or 100
        price = (float(amount) / float(divisor)) if amount is not None else None
        images = listing.get("images") or []
        image = next(
            (str(item.get("url_fullxfull") or item.get("url_570xN") or "") for item in images if isinstance(item, dict)),
            "",
        )
        taxonomy = str(listing.get("taxonomy_path") or listing.get("type") or "uncategorized")
        if isinstance(listing.get("taxonomy_path"), list):
            taxonomy = " > ".join(map(str, listing["taxonomy_path"]))
        return Product(
            project_id=listing_id,
            source_platform=self.source_name,
            url=url,
            title=title,
            description=str(listing.get("description") or "").strip(),
            category=taxonomy or "uncategorized",
            image_url=image or url,
            raw_data={
                "listing_id": listing_id,
                "discovery_query": query,
                "price": price,
                "currency": price_data.get("currency_code"),
                "views": listing.get("views"),
                "favorite_count": listing.get("num_favorers"),
                "shop_id": listing.get("shop_id"),
                "taxonomy": taxonomy,
                "tags": listing.get("tags") or [],
                "is_digital": listing.get("is_digital"),
                "state": listing.get("state"),
                "created_timestamp": listing.get("original_creation_timestamp"),
                "updated_timestamp": listing.get("last_modified_timestamp"),
                "user_feedback_available": False,
            },
        )
