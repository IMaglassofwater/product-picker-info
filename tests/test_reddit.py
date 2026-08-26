"""Tests for the public Reddit RSS scraper."""

import urllib.error

import pytest

from models import Product
from scrapers.base_scraper import ScraperFetchError
from scrapers.reddit import RedditScraper


MOCK_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>t3_abc123</id>
    <title>Compact everyday carry organizer</title>
    <link href="https://www.reddit.com/r/EDC/comments/abc123/example/" />
    <content type="html">&lt;p&gt;A small organizer.&lt;/p&gt;&lt;img src="https://example.com/product.jpg" /&gt;</content>
  </entry>
</feed>
"""


def test_fetch_generates_product_from_mock_rss(monkeypatch):
    scraper = RedditScraper()
    monkeypatch.setattr(scraper, "_fetch_feed", lambda _url: MOCK_RSS)

    products = scraper.fetch()

    assert products
    assert isinstance(products[0], Product)
    assert products[0].source_platform == "reddit"
    assert products[0].url
    assert products[0].title == "Compact everyday carry organizer"


def test_network_failure_raises_scraper_fetch_error(monkeypatch):
    scraper = RedditScraper()

    def fail(_url):
        raise ScraperFetchError("network unavailable")

    monkeypatch.setattr(scraper, "_fetch_feed", fail)

    with pytest.raises(ScraperFetchError):
        scraper.fetch()


def test_http_failure_retries_and_reports_status(monkeypatch):
    scraper = RedditScraper()
    attempts = 0

    def fail(_request, timeout):
        nonlocal attempts
        attempts += 1
        assert timeout == scraper.REQUEST_TIMEOUT
        raise urllib.error.HTTPError(
            "https://www.reddit.com/r/EDC/.rss",
            503,
            "Service Unavailable",
            None,
            None,
        )

    monkeypatch.setattr("scrapers.reddit.urllib.request.urlopen", fail)
    monkeypatch.setattr("scrapers.reddit.time.sleep", lambda _seconds: None)

    with pytest.raises(ScraperFetchError) as error:
        scraper._fetch_feed("https://www.reddit.com/r/EDC/.rss")

    assert attempts == scraper.MAX_RETRIES
    assert "HTTP status: 503" in str(error.value)
    assert "Service Unavailable" in str(error.value)
