"""Product Hunt scraper using public RSS and public page metadata."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from models import Product
from scrapers.base_scraper import BaseScraper, ScraperFetchError


class _EntryContentParser(HTMLParser):
    """Extract plain text and the first image from RSS entry HTML."""

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
        source = dict(attrs).get("src")
        if source and source.startswith(("http://", "https://")):
            self.image_url = source

    @property
    def text(self) -> str:
        return " ".join(self.text_parts)


class _StructuredMetadataParser(HTMLParser):
    """Collect JSON-LD, meta tags, and canonical links without CSS selectors."""

    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, list[str]] = {}
        self.canonical_url = ""
        self.json_ld: list[Any] = []
        self._in_json_ld = False
        self._json_ld_parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = {key.lower(): value for key, value in attrs}
        if tag.lower() == "meta":
            key = attributes.get("property") or attributes.get("name")
            content = attributes.get("content")
            if key and content:
                self.meta.setdefault(key.lower(), []).append(content.strip())
        elif tag.lower() == "link":
            rel = (attributes.get("rel") or "").lower().split()
            href = attributes.get("href") or ""
            if "canonical" in rel and href.startswith(("http://", "https://")):
                self.canonical_url = href
        elif (
            tag.lower() == "script"
            and (attributes.get("type") or "").lower() == "application/ld+json"
        ):
            self._in_json_ld = True
            self._json_ld_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._json_ld_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "script" or not self._in_json_ld:
            return
        self._in_json_ld = False
        payload = "".join(self._json_ld_parts).strip()
        if payload:
            try:
                self.json_ld.append(json.loads(payload))
            except json.JSONDecodeError:
                pass


class ProductHuntScraper(BaseScraper):
    """Normalize Product Hunt RSS entries enriched by public page metadata."""

    FEED_URL = "https://www.producthunt.com/feed"
    USER_AGENT = "ProductPicker/0.1 (public metadata reader)"
    REQUEST_TIMEOUT = 15

    @property
    def source_name(self) -> str:
        return "product_hunt"

    def fetch(self) -> list[Product]:
        """Fetch RSS products and enrich each from its public product page."""
        feed_data = self._fetch_feed()
        try:
            root = ET.fromstring(feed_data)
        except ET.ParseError as exc:
            raise ScraperFetchError(
                f"Product Hunt RSS parsing failed: {exc}"
            ) from exc

        entries = self._entries(root)
        if not entries:
            raise ScraperFetchError("Product Hunt RSS returned no entries")

        products: list[Product] = []
        enrichment_available = True
        unavailable_reason = ""
        for entry in entries:
            try:
                product = self._parse_entry(entry)
            except (KeyError, TypeError, ValueError):
                continue

            if enrichment_available:
                try:
                    page_data = self._fetch_product_page(product.url)
                    metadata = self._parse_public_metadata(page_data, product.url)
                    self._apply_metadata(product, metadata)
                except ScraperFetchError as exc:
                    enrichment_available = False
                    unavailable_reason = str(exc)
                    product.raw_data["metadata_error"] = unavailable_reason
                except (TypeError, ValueError) as exc:
                    product.raw_data["metadata_error"] = str(exc)
            elif unavailable_reason:
                product.raw_data["metadata_error"] = unavailable_reason
            products.append(product)

        if not products:
            raise ScraperFetchError(
                "Product Hunt RSS contained no valid product entries"
            )
        return products

    def _fetch_feed(self) -> bytes:
        return self._fetch_url(self.FEED_URL, "Product Hunt RSS")

    def _fetch_product_page(self, product_url: str) -> bytes:
        return self._fetch_url(product_url, "Product Hunt product page")

    def _fetch_url(self, url: str, label: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self.USER_AGENT},
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.REQUEST_TIMEOUT
            ) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise ScraperFetchError(
                f"{label} request failed; HTTP status: {exc.code}; "
                f"reason: {exc.reason}"
            ) from exc
        except (OSError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", None) or str(exc)
            raise ScraperFetchError(
                f"{label} request failed; HTTP status: unavailable; "
                f"reason: {reason}"
            ) from exc

    @staticmethod
    def _entries(root: ET.Element) -> list[ET.Element]:
        return [
            element
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1] in {"entry", "item"}
        ]

    def _parse_entry(self, entry: ET.Element) -> Product:
        title = self._text(entry, "title")
        entry_id = self._text(entry, "id", required=False) or self._text(
            entry, "guid", required=False
        )
        product_hunt_url = self._link(entry)
        project_id = self._project_id(entry_id, product_hunt_url)
        content = self._text(entry, "content", required=False) or self._text(
            entry, "description", required=False
        )
        rss_category = self._category(entry)

        parser = _EntryContentParser()
        parser.feed(content)
        tagline = self._clean_tagline(parser.text)
        image_url = parser.image_url

        product = Product(
            project_id=project_id,
            source_platform=self.source_name,
            url=product_hunt_url,
            title=title,
            description=tagline or title,
            category=rss_category,
            image_url=image_url or product_hunt_url,
            raw_data={
                "id": entry_id,
                "title": title,
                "tagline": tagline,
                "topics": [] if rss_category == "uncategorized" else [rss_category],
                "website": "",
                "product_hunt_url": product_hunt_url,
                "metadata": {},
                "rss_content": content,
            },
        )
        if not image_url:
            product.image_url = ""
        return product

    @classmethod
    def _parse_public_metadata(
        cls, page_data: bytes, product_hunt_url: str
    ) -> dict[str, Any]:
        parser = _StructuredMetadataParser()
        parser.feed(page_data.decode("utf-8", errors="replace"))

        topics = cls._metadata_topics(parser)
        description = cls._first_meta(
            parser.meta, "og:description", "twitter:description", "description"
        )
        image = cls._first_meta(parser.meta, "og:image", "twitter:image")
        website = cls._external_website(parser.json_ld, product_hunt_url)
        makers = cls._json_ld_values(parser.json_ld, {"author", "creator", "brand"})
        platforms = cls._json_ld_values(
            parser.json_ld, {"operatingSystem", "applicationCategory", "@type"}
        )

        return {
            "topics": topics,
            "description": description,
            "website": website,
            "image": image,
            "metadata": {
                "open_graph": {
                    key: values
                    for key, values in parser.meta.items()
                    if key.startswith("og:") and values
                },
                "makers": makers,
                "platforms": platforms,
                "canonical_url": parser.canonical_url,
                "json_ld": parser.json_ld,
            },
        }

    @staticmethod
    def _apply_metadata(product: Product, metadata: dict[str, Any]) -> None:
        topics = metadata.get("topics") or []
        richer_description = (metadata.get("description") or "").strip()
        website = (metadata.get("website") or "").strip()
        image = (metadata.get("image") or "").strip()

        product.raw_data["topics"] = topics
        product.raw_data["website"] = website
        product.raw_data["metadata"] = metadata.get("metadata") or {}
        if richer_description:
            product.raw_data["richer_description"] = richer_description
            if len(richer_description) > len(product.description):
                product.description = richer_description
        if topics:
            product.category = topics[0]
        if image:
            product.image_url = image

    @classmethod
    def _metadata_topics(cls, parser: _StructuredMetadataParser) -> list[str]:
        topics: list[str] = []
        for key in ("article:tag", "product:category"):
            topics.extend(parser.meta.get(key, []))
        topics.extend(
            cls._json_ld_values(
                parser.json_ld,
                {"keywords", "applicationCategory", "category", "genre"},
            )
        )
        return cls._unique_strings(topics)

    @classmethod
    def _json_ld_values(
        cls, nodes: list[Any], keys: set[str]
    ) -> list[str]:
        values: list[str] = []

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                for key, nested in value.items():
                    if key in keys:
                        values.extend(cls._flatten_strings(nested))
                    visit(nested)
            elif isinstance(value, list):
                for nested in value:
                    visit(nested)

        visit(nodes)
        return cls._unique_strings(values)

    @classmethod
    def _external_website(
        cls, nodes: list[Any], product_hunt_url: str
    ) -> str:
        product_hunt_host = urlparse(product_hunt_url).netloc.lower()
        for candidate in cls._json_ld_values(nodes, {"sameAs", "url"}):
            parsed = urlparse(candidate)
            if (
                parsed.scheme in {"http", "https"}
                and parsed.netloc
                and parsed.netloc.lower() != product_hunt_host
                and not parsed.netloc.lower().endswith(".producthunt.com")
            ):
                return candidate
        return ""

    @staticmethod
    def _flatten_strings(value: Any) -> list[str]:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            result: list[str] = []
            for item in value:
                result.extend(ProductHuntScraper._flatten_strings(item))
            return result
        if isinstance(value, dict):
            for key in ("name", "url"):
                if isinstance(value.get(key), str):
                    return [value[key].strip()]
        return []

    @staticmethod
    def _unique_strings(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = value.strip()
            key = normalized.casefold()
            if normalized and key not in seen:
                seen.add(key)
                result.append(normalized)
        return result

    @staticmethod
    def _first_meta(meta: dict[str, list[str]], *keys: str) -> str:
        for key in keys:
            values = meta.get(key, [])
            if values:
                return values[0]
        return ""

    @staticmethod
    def _clean_tagline(text: str) -> str:
        for suffix in ("Discussion | Link", "Discussion", "| Link"):
            if text.endswith(suffix):
                text = text[: -len(suffix)].rstrip()
        return text

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
            raise ValueError(f"Missing Product Hunt RSS field: {local_name}")
        return ""

    @staticmethod
    def _link(entry: ET.Element) -> str:
        for child in entry:
            if child.tag.rsplit("}", 1)[-1] != "link":
                continue
            url = (child.get("href") or child.text or "").strip()
            if url.startswith(("http://", "https://")):
                return url
        raise ValueError("Missing valid Product Hunt product link")

    @staticmethod
    def _category(entry: ET.Element) -> str:
        for child in entry:
            if child.tag.rsplit("}", 1)[-1] != "category":
                continue
            category = (child.get("term") or child.text or "").strip()
            if category:
                return category
        return "uncategorized"

    @staticmethod
    def _project_id(entry_id: str, url: str) -> str:
        if entry_id:
            return entry_id
        path_parts = [part for part in urlparse(url).path.split("/") if part]
        if path_parts:
            return path_parts[-1]
        raise ValueError("Missing Product Hunt unique identifier")
