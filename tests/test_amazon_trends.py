"""Offline tests for the bounded Amazon trend source."""

import urllib.error

import pytest

from scrapers.amazon_trends import AmazonTrendScraper, filter_amazon_trend
from scrapers.base_scraper import ScraperFetchError


def _card(
    asin: str = "B0ABC12345",
    title: str = "Compact Desk Organizer Tray",
    rank: int = 3,
    extra: str = "",
) -> str:
    return f"""
    <div class="zg-grid-general-faceout" data-asin="{asin}">
      <span class="zg-bdg-text">#{rank}</span>
      <div class="p13n-sc-css-line-clamp-2">{title}</div>
      <img alt="{title}" src="https://images.example.com/{asin}.jpg">
      <span class="p13n-sc-price">$12.99</span>
      <span>4.6 out of 5 stars</span><a>245 ratings</a>{extra}
    </div>
    """


def test_new_releases_maps_required_product_fields():
    products = AmazonTrendScraper.parse_page(
        _card(), "new_releases", "Home & Kitchen"
    )
    product = products[0]

    assert product.source_platform == "amazon"
    assert product.title == "Compact Desk Organizer Tray"
    assert product.url == "https://www.amazon.com/dp/B0ABC12345"
    assert product.raw_data == {
        "asin": "B0ABC12345", "rank": 3, "rank_change": None,
        "price": "$12.99", "rating": 4.6, "review_count": 245,
        "category": "Home & Kitchen",
        "image_url": "https://images.example.com/B0ABC12345.jpg",
        "source_list": "new_releases",
    }


def test_movers_parses_rank_change_when_publicly_present():
    product = AmazonTrendScraper.parse_page(
        _card(extra="<span>Moved Up 42 spots</span>"),
        "movers_and_shakers", "Home & Kitchen",
    )[0]
    assert product.raw_data["rank_change"] == 42


def test_missing_optional_fields_remain_none():
    payload = '<div data-asin="B0XYZ12345"><img alt="Plain Storage Basket"></div>'
    raw = AmazonTrendScraper.parse_page(payload, "new_releases", "Home")[0].raw_data
    assert raw["price"] is None
    assert raw["rating"] is None
    assert raw["review_count"] is None
    assert raw["rank_change"] is None


def test_simple_physical_filter_accepts_storage_product():
    product = AmazonTrendScraper.parse_page(
        _card(title="Lightweight Storage Basket"), "new_releases", "Home"
    )[0]
    result = filter_amazon_trend(product)
    assert result.status == "candidate"
    assert result.product_type == "simple_physical"
    assert result.theme == "storage_and_organization"


@pytest.mark.parametrize(
    "title, expected_type",
    [
        ("Wireless Robot Camera", "complex_electronics"),
        ("Vitamin Food Supplement", "regulated"),
        ("King Bed Frame", "large_or_heavy"),
        ("Digital Download Software", "software_or_digital"),
    ],
)
def test_high_confidence_non_simple_products_are_rejected(title, expected_type):
    product = AmazonTrendScraper.parse_page(_card(title=title), "new_releases", "Home")[0]
    result = filter_amazon_trend(product)
    assert result.status == "rejected"
    assert result.product_type == expected_type


def test_no_duplicate_asin_across_lists(monkeypatch):
    pages = (("new_releases", "Home", "https://example.com/new"),
             ("movers_and_shakers", "Home", "https://example.com/movers"))
    scraper = AmazonTrendScraper(pages)
    monkeypatch.setattr(scraper, "_request", lambda _url: _card())
    assert len(scraper.fetch()) == 1


def test_failed_page_retries_once_and_other_page_continues(monkeypatch):
    pages = (("new_releases", "Home", "bad"), ("movers_and_shakers", "Home", "good"))
    scraper = AmazonTrendScraper(pages)
    calls = []

    def request(url):
        calls.append(url)
        scraper.request_count += 1
        if url == "bad":
            raise ScraperFetchError("HTTP status 503; reason: unavailable")
        return _card(extra="Moved Up 2 spots")

    monkeypatch.setattr(scraper, "_request", request)
    products = scraper.fetch()
    assert len(products) == 1
    assert calls == ["bad", "bad", "good"]
    assert scraper.failed_pages == 1


def test_total_request_limit_is_never_exceeded(monkeypatch):
    pages = tuple(("new_releases", "Home", str(i)) for i in range(20))
    scraper = AmazonTrendScraper(pages)

    def fail(_url):
        scraper.request_count += 1
        raise ScraperFetchError("blocked")

    monkeypatch.setattr(scraper, "_request", fail)
    with pytest.raises(ScraperFetchError):
        scraper.fetch()
    assert scraper.request_count == 10


def test_http_error_becomes_scraper_fetch_error(monkeypatch):
    scraper = AmazonTrendScraper()
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
        ),
    )
    with pytest.raises(ScraperFetchError, match="HTTP status 429"):
        scraper._request("https://example.com")
