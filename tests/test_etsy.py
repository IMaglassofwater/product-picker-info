import json
from unittest.mock import patch

import pytest

from evidence_foundation import classify_concrete_product, classify_eligibility, normalize_identity
from scrapers.base_scraper import ScraperFetchError
from scrapers.etsy import EtsyScraper


def listing(digital=False):
    return {
        "listing_id": 123,
        "title": "Personalized Leather Travel Wallet Passport Holder RFID Blocking Handmade Gift for Him",
        "description": "A handmade leather passport wallet.",
        "url": "https://www.etsy.com/listing/123/wallet",
        "price": {"amount": 4200, "divisor": 100, "currency_code": "USD"},
        "views": 800,
        "num_favorers": 25,
        "shop_id": 9,
        "taxonomy_path": ["Bags", "Wallets"],
        "tags": ["travel wallet"],
        "is_digital": digital,
        "state": "active",
    }


def test_etsy_maps_official_listing_and_normalizes_seo_title(monkeypatch):
    monkeypatch.setenv("ETSY_API_KEY", "test-key")
    monkeypatch.setenv("ETSY_SHARED_SECRET", "test-secret")
    scraper = EtsyScraper(personal_approval_granted=True)
    with patch.object(scraper, "_request_query", return_value={"results": [listing()] } ):
        products = scraper.fetch()
    item = products[0]
    assert item.source_platform == "etsy" and item.raw_data["price"] == 42
    eligibility = classify_eligibility(item)
    assert eligibility.eligibility_status == "ELIGIBLE"
    assert classify_concrete_product(item, eligibility).status == "CONCRETE"
    assert normalize_identity(item, eligibility).normalized_product_name == "Leather Passport Travel Wallet"


def test_etsy_digital_listing_is_ineligible():
    item = EtsyScraper(personal_approval_granted=True)._parse_listing(listing(True), "stationery")
    assert classify_eligibility(item).eligibility_status == "INELIGIBLE"


def test_etsy_missing_credentials_is_explicit(monkeypatch):
    monkeypatch.delenv("ETSY_API_KEY", raising=False)
    monkeypatch.delenv("ETSY_SHARED_SECRET", raising=False)
    with pytest.raises(ScraperFetchError, match="must be configured"):
        EtsyScraper(personal_approval_granted=True).fetch()


def test_etsy_is_deferred_before_personal_approval():
    with pytest.raises(ScraperFetchError, match="DEFERRED_PENDING_PERSONAL_APPROVAL"):
        EtsyScraper(personal_approval_granted=False).fetch()
