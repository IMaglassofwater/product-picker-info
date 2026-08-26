"""Tests for the public RSS-only Yanko Design scraper."""

import urllib.error

import pytest

from scrapers.base_scraper import ScraperFetchError
from scrapers.yanko_design import YankoDesignScraper


MOCK_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>Yanko Design</title>
    <item>
      <title>Compact Modular Travel Pouch</title>
      <link>https://www.yankodesign.com/2026/08/25/compact-pouch/?utm_source=rss</link>
      <guid>yanko-101</guid>
      <pubDate>Tue, 25 Aug 2026 08:00:00 +0000</pubDate>
      <category>Product Design</category>
      <category>Accessories</category>
      <description><![CDATA[Compact Modular Travel Pouch A simple non-electronic pouch with modular pockets for daily travel.]]></description>
      <media:content url="https://www.yankodesign.com/images/pouch.jpg" type="image/jpeg" />
    </item>
    <item>
      <title>Broken entry without link</title>
      <description>Skipped safely</description>
    </item>
  </channel>
</rss>"""


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.payload


def test_rss_parses_product_and_core_fields(monkeypatch):
    monkeypatch.setattr(
        "scrapers.yanko_design.urllib.request.urlopen",
        lambda _request, timeout: _Response(MOCK_RSS),
    )

    products = YankoDesignScraper().fetch()

    assert len(products) == 1
    product = products[0]
    assert product.source_platform == "yanko_design"
    assert product.title == "Compact Modular Travel Pouch"
    assert product.url == "https://www.yankodesign.com/2026/08/25/compact-pouch/"
    assert "simple non-electronic pouch" in product.description
    assert product.image_url.endswith("pouch.jpg")


def test_categories_tags_and_public_metadata_are_preserved(monkeypatch):
    monkeypatch.setattr(
        "scrapers.yanko_design.urllib.request.urlopen",
        lambda _request, timeout: _Response(MOCK_RSS),
    )

    product = YankoDesignScraper().fetch()[0]

    assert product.category == "Product Design"
    assert product.raw_data["categories"] == ["Product Design", "Accessories"]
    assert product.raw_data["tags"] == ["Product Design", "Accessories"]
    assert product.raw_data["published_at"] == "Tue, 25 Aug 2026 08:00:00 +0000"
    assert product.raw_data["image_url"].endswith("pouch.jpg")


def test_network_failure_becomes_scraper_fetch_error(monkeypatch):
    def fail(_request, timeout):
        raise urllib.error.URLError("feed unavailable")

    monkeypatch.setattr("scrapers.yanko_design.urllib.request.urlopen", fail)

    with pytest.raises(ScraperFetchError) as error:
        YankoDesignScraper().fetch()

    assert "HTTP status: unavailable" in str(error.value)
    assert "feed unavailable" in str(error.value)
