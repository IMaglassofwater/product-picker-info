"""Tests for the KSInsights-backed Kickstarter adapter."""

import urllib.error

import pytest

from models import Product
from scrapers.base_scraper import ScraperFetchError
from scrapers.kickstarter import KickstarterScraper


MOCK_CSV = b"""id,name,blurb,project_url,category_name,category_parent_name,backers_count,goal,pledged,percent_funded,currency,state,deadline,launched_at,creator_name,country
1001,Compact EDC Tool,A lightweight everyday tool.,https://www.kickstarter.com/projects/example/compact-edc-tool,Product Design,Design,420,10000,25000,250,USD,live,2026-09-30,2026-08-01,Example Maker,US
,Broken Project,Missing its id.,https://www.kickstarter.com/projects/example/broken,Design,Design,1,100,10,10,USD,live,2026-09-30,2026-08-01,Broken Maker,US
1002,Travel Desk Stand,A portable desk stand.,https://www.kickstarter.com/projects/example/travel-desk-stand,Design,Design,50,5000,2500,50,USD,successful,2026-08-20,2026-07-01,Second Maker,GB
"""


def _mock_scraper(monkeypatch) -> KickstarterScraper:
    scraper = KickstarterScraper()
    indexes = iter(
        [
            [
                {"name": "20250807", "type": "dir", "url": "old-index"},
                {"name": "20250808", "type": "dir", "url": "latest-index"},
            ],
            [
                {
                    "name": "items_live_daily_20250808.csv",
                    "download_url": "mock-csv-url",
                }
            ],
        ]
    )
    monkeypatch.setattr(scraper, "_fetch_json", lambda _url: next(indexes))
    monkeypatch.setattr(scraper, "_fetch_bytes", lambda _url: MOCK_CSV)
    return scraper


def test_ksinsights_product_mapping(monkeypatch):
    product = _mock_scraper(monkeypatch).fetch()[0]

    assert isinstance(product, Product)
    assert product.project_id == "1001"
    assert product.source_platform == "kickstarter"
    assert product.title == "Compact EDC Tool"
    assert product.description == "A lightweight everyday tool."
    assert product.category == "Product Design"
    assert product.url == (
        "https://www.kickstarter.com/projects/example/compact-edc-tool"
    )


def test_ksinsights_market_fields_are_preserved(monkeypatch):
    raw_data = _mock_scraper(monkeypatch).fetch()[0].raw_data

    assert raw_data["goal"] == 10000
    assert raw_data["pledged"] == 25000
    assert raw_data["percent_funded"] == 250
    assert raw_data["backers_count"] == 420
    assert raw_data["creator_name"] == "Example Maker"


def test_invalid_record_does_not_break_valid_projects(monkeypatch):
    products = _mock_scraper(monkeypatch).fetch()

    assert [product.project_id for product in products] == ["1001", "1002"]


def test_network_error_becomes_scraper_fetch_error(monkeypatch):
    scraper = KickstarterScraper()

    def fail(_request, timeout):
        assert timeout == scraper.REQUEST_TIMEOUT
        raise urllib.error.HTTPError(
            scraper.DAILY_INDEX_URL, 503, "Service Unavailable", None, None
        )

    monkeypatch.setattr("scrapers.kickstarter.urllib.request.urlopen", fail)

    with pytest.raises(ScraperFetchError) as error:
        scraper.fetch()

    assert "HTTP status: 503" in str(error.value)
    assert "Service Unavailable" in str(error.value)
