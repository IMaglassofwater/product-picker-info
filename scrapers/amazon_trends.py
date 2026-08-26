"""Lightweight Amazon public trend-list collector for isolated validation."""

from __future__ import annotations

from dataclasses import dataclass
import html
import re
import urllib.error
import urllib.request

from models import Product
from scrapers.base_scraper import BaseScraper, ScraperFetchError


@dataclass(frozen=True)
class AmazonTrendResult:
    """Free-rule result used only by the Amazon trend validation flow."""

    status: str
    product_type: str
    theme: str
    feasibility_score: int
    market_signal_score: int
    micro_innovation_score: int
    signals: list[str]
    reason: str


class AmazonTrendScraper(BaseScraper):
    """Read a bounded set of public Amazon trend list pages."""

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    )
    REQUEST_TIMEOUT = 15
    MAX_REQUESTS = 10
    MAX_RETRIES = 1
    MAX_PRODUCTS = 30
    LIST_PAGES = (
        (
            "new_releases",
            "Home & Kitchen",
            "https://www.amazon.com/gp/new-releases/home-garden",
        ),
        (
            "movers_and_shakers",
            "Home & Kitchen",
            "https://www.amazon.com/gp/movers-and-shakers/home-garden",
        ),
    )

    def __init__(self, list_pages: tuple[tuple[str, str, str], ...] | None = None):
        self.list_pages = list_pages or self.LIST_PAGES
        self.request_count = 0
        self.successful_pages = 0
        self.failed_pages = 0
        self.failures: list[str] = []
        self.source_counts = {"new_releases": 0, "movers_and_shakers": 0}

    @property
    def source_name(self) -> str:
        return "amazon"

    def fetch(self) -> list[Product]:
        """Fetch configured public lists, independently handling page failures."""
        products: list[Product] = []
        seen: set[str] = set()
        for source_list, category, url in self.list_pages:
            if self.request_count >= self.MAX_REQUESTS:
                break
            page_products: list[Product] = []
            last_error = "page returned no parseable products"
            for attempt in range(self.MAX_RETRIES + 1):
                if self.request_count >= self.MAX_REQUESTS:
                    break
                try:
                    payload = self._request(url)
                    page_products = self.parse_page(payload, source_list, category)
                    if page_products:
                        break
                except ScraperFetchError as exc:
                    last_error = str(exc)
                if attempt == self.MAX_RETRIES:
                    break
            if not page_products:
                self.failed_pages += 1
                self.failures.append(f"{source_list}: {last_error}")
                continue
            self.successful_pages += 1
            for product in page_products:
                if product.url in seen or len(products) >= self.MAX_PRODUCTS:
                    continue
                seen.add(product.url)
                products.append(product)
                self.source_counts[source_list] = self.source_counts.get(source_list, 0) + 1
        if not products:
            reason = "; ".join(self.failures) or "no pages could be requested"
            raise ScraperFetchError(f"Amazon trend lists unavailable: {reason}")
        return products

    def _request(self, url: str) -> str:
        self.request_count += 1
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.REQUEST_TIMEOUT) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise ScraperFetchError(
                f"HTTP status {exc.code}; reason: {exc.reason}"
            ) from exc
        except (OSError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", None) or str(exc)
            raise ScraperFetchError(
                f"HTTP status unavailable; reason: {reason}"
            ) from exc

    @classmethod
    def parse_page(
        cls, payload: str, source_list: str, category: str
    ) -> list[Product]:
        """Parse product cards using stable public attributes, without detail pages."""
        starts = list(re.finditer(r'<div\b[^>]*\bdata-asin=["\']([^"\']+)["\']', payload, re.I))
        products: list[Product] = []
        for index, match in enumerate(starts):
            asin = match.group(1).strip()
            if not re.fullmatch(r"[A-Z0-9]{10}", asin, re.I):
                continue
            end = starts[index + 1].start() if index + 1 < len(starts) else len(payload)
            card = payload[match.start():end]
            title = cls._extract_title(card)
            if not title:
                continue
            rank = cls._integer(cls._match(card, r'zg-bdg-text[^>]*>\s*#?([\d,]+)'))
            price = cls._match(card, r'p13n-sc-price[^>]*>\s*([^<]+)') or None
            rating_text = cls._match(card, r'([\d.]+)\s+out of 5 stars')
            review_text = cls._match(card, r'([\d,]+)\s+(?:ratings?|reviews?)')
            image_url = cls._match(card, r'<img\b[^>]*\bsrc=["\']([^"\']+)["\']')
            rank_change = cls._rank_change(card)
            url = f"https://www.amazon.com/dp/{asin.upper()}"
            raw_data = {
                "asin": asin.upper(),
                "rank": rank,
                "rank_change": rank_change,
                "price": " ".join(html.unescape(price).split()) if price else None,
                "rating": float(rating_text) if rating_text else None,
                "review_count": cls._integer(review_text),
                "category": category,
                "image_url": html.unescape(image_url) if image_url else None,
                "source_list": source_list,
            }
            product = Product(
                project_id=asin.upper(),
                source_platform="amazon",
                url=url,
                title=title,
                description=title,
                category=category,
                image_url=raw_data["image_url"] or url,
                raw_data=raw_data,
            )
            if not raw_data["image_url"]:
                product.image_url = ""
            products.append(product)
        return products

    @classmethod
    def _extract_title(cls, card: str) -> str:
        value = cls._match(
            card,
            r'p13n-sc-css-line-clamp[^>]*>(.*?)</div>',
            flags=re.I | re.S,
        )
        if not value:
            value = cls._match(card, r'<img\b[^>]*\balt=["\']([^"\']+)["\']')
        if not value:
            return ""
        clean = re.sub(r"<[^>]+>", " ", value)
        return " ".join(html.unescape(clean).split())

    @staticmethod
    def _match(text: str, pattern: str, flags: int = re.I) -> str:
        match = re.search(pattern, text, flags)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _integer(value: str) -> int | None:
        try:
            return int(value.replace(",", "")) if value else None
        except ValueError:
            return None

    @classmethod
    def _rank_change(cls, card: str) -> int | float | None:
        moved = cls._match(card, r'Moved\s+Up\s+([\d,]+)')
        if moved:
            return cls._integer(moved)
        percent = cls._match(card, r'([\d,.]+)\s*%')
        try:
            return float(percent.replace(",", "")) if percent else None
        except ValueError:
            return None


def filter_amazon_trend(product: Product) -> AmazonTrendResult:
    """Apply small, high-confidence rules to public trend-list metadata."""
    text = f"{product.title} {product.category}".casefold()
    groups = {
        "regulated": ("supplement", "medicine", "medical", "food", "pesticide", "repellent"),
        "complex_electronics": ("bluetooth", "wireless", "battery", "electric", "robot", "charger", "camera"),
        "large_or_heavy": ("bed frame", "mattress", "refrigerator", "gaming chair", "floor mirror"),
        "software_or_digital": ("software", "digital download", "app subscription"),
    }
    for product_type, terms in groups.items():
        if any(term in text for term in terms):
            return AmazonTrendResult(
                "rejected", product_type, "other", 20, _market_signal(product), 10,
                [product_type], f"high-confidence {product_type} signal",
            )

    theme = _theme(text)
    simple_terms = (
        "organizer", "storage", "basket", "container", "pouch", "bag", "rack",
        "holder", "brush", "towel", "mat", "cover", "hook", "tray", "bottle",
        "notebook", "toy", "leash", "collar", "tool", "shelf", "curtain",
    )
    signals = ["public_trend_list"]
    if any(term in text for term in simple_terms):
        signals.extend(("simple_physical", "common_consumer_category"))
        if product.raw_data.get("source_list") == "movers_and_shakers":
            signals.append("movers_signal")
        else:
            signals.append("new_release_signal")
        return AmazonTrendResult(
            "candidate", "simple_physical", theme, 70,
            _market_signal(product), 55, signals,
            "simple physical trend item; supplier and demand validation still required",
        )
    return AmazonTrendResult(
        "uncertain", "other", theme, 45, _market_signal(product), 30,
        signals, "insufficient public list metadata for a confident simple-product decision",
    )


def _market_signal(product: Product) -> int:
    raw = product.raw_data
    score = 45 if raw.get("source_list") == "new_releases" else 50
    rank = raw.get("rank")
    if isinstance(rank, int):
        score += 25 if rank <= 10 else 18 if rank <= 30 else 10
    if raw.get("rank_change") is not None:
        score += 10
    if isinstance(raw.get("rating"), (int, float)) and raw["rating"] >= 4:
        score += 5
    reviews = raw.get("review_count")
    if isinstance(reviews, int):
        score += 10 if reviews >= 200 else 5 if reviews >= 20 else 0
    return min(100, score)


def _theme(text: str) -> str:
    mappings = (
        ("storage_and_organization", ("organizer", "storage", "basket", "container", "rack", "holder", "shelf")),
        ("bags_and_carry", ("bag", "pouch", "backpack", "tote")),
        ("pet_accessories", ("pet", "dog", "cat", "leash", "collar")),
        ("desk_and_office", ("desk", "office", "notebook", "pen")),
        ("outdoor_accessories", ("outdoor", "camping", "garden")),
        ("tools_and_edc", ("tool", "hook", "flashlight")),
        ("home_and_living", ("home", "kitchen", "bath", "towel", "mat", "curtain")),
    )
    for theme, terms in mappings:
        if any(term in text for term in terms):
            return theme
    return "other"
