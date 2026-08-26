"""Tests for the Product Hunt public RSS scraper."""

import urllib.error

import pytest

from models import Product
from scrapers.base_scraper import ScraperFetchError
from scrapers.product_hunt import ProductHuntScraper


MOCK_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>product-hunt-123</id>
    <title>Focus Desk</title>
    <link href="https://www.producthunt.com/posts/focus-desk" />
    <content type="html">&lt;p&gt;A compact productivity desk tool.&lt;/p&gt;&lt;img src="https://example.com/focus-desk.png" /&gt;</content>
    <category term="productivity" />
  </entry>
</feed>
"""

MOCK_HTML = b"""<!doctype html>
<html>
<head>
  <link rel="canonical" href="https://www.producthunt.com/posts/focus-desk" />
  <meta property="og:description" content="A richer description for planning focused work at a compact desk." />
  <meta property="og:image" content="https://example.com/focus-desk-large.png" />
  <meta property="article:tag" content="Productivity" />
  <script type="application/ld+json">
  {
    "@type": "SoftwareApplication",
    "name": "Focus Desk",
    "applicationCategory": "Desk Tools",
    "keywords": ["Productivity", "Workspace"],
    "url": "https://focusdesk.example.com",
    "author": {"@type": "Organization", "name": "Focus Maker"}
  }
  </script>
</head>
</html>"""


def _mock_public_sources(scraper, monkeypatch):
    monkeypatch.setattr(scraper, "_fetch_feed", lambda: MOCK_RSS)
    monkeypatch.setattr(
        scraper, "_fetch_product_page", lambda _url: MOCK_HTML
    )


def test_fetch_generates_product_from_mock_rss(monkeypatch):
    scraper = ProductHuntScraper()
    _mock_public_sources(scraper, monkeypatch)

    products = scraper.fetch()

    assert len(products) == 1
    assert isinstance(products[0], Product)


def test_product_fields_are_mapped_correctly(monkeypatch):
    scraper = ProductHuntScraper()
    _mock_public_sources(scraper, monkeypatch)

    product = scraper.fetch()[0]

    assert product.project_id == "product-hunt-123"
    assert product.source_platform == "product_hunt"
    assert product.url == "https://www.producthunt.com/posts/focus-desk"
    assert product.title == "Focus Desk"
    assert product.description == (
        "A richer description for planning focused work at a compact desk."
    )
    assert product.category == "Productivity"
    assert product.image_url == "https://example.com/focus-desk-large.png"
    assert product.raw_data["id"] == "product-hunt-123"


def test_public_metadata_is_saved_in_raw_data(monkeypatch):
    scraper = ProductHuntScraper()
    _mock_public_sources(scraper, monkeypatch)

    product = scraper.fetch()[0]

    assert product.raw_data["tagline"] == "A compact productivity desk tool."
    assert product.raw_data["topics"] == [
        "Productivity",
        "Desk Tools",
        "Workspace",
    ]
    assert product.raw_data["website"] == "https://focusdesk.example.com"
    assert product.raw_data["product_hunt_url"] == product.url
    assert product.raw_data["metadata"]["makers"] == ["Focus Maker"]
    assert "SoftwareApplication" in product.raw_data["metadata"]["platforms"]


def test_network_error_is_reported(monkeypatch):
    scraper = ProductHuntScraper()

    def fail(_request, timeout):
        assert timeout == scraper.REQUEST_TIMEOUT
        raise urllib.error.HTTPError(
            scraper.FEED_URL, 503, "Service Unavailable", None, None
        )

    monkeypatch.setattr("scrapers.product_hunt.urllib.request.urlopen", fail)

    with pytest.raises(ScraperFetchError) as error:
        scraper.fetch()

    assert "HTTP status: 503" in str(error.value)
    assert "Service Unavailable" in str(error.value)
