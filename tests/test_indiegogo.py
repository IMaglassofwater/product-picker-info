"""Offline tests for the official-public-API Indiegogo adapter."""

import json
import urllib.error

import pytest

from scrapers.base_scraper import ScraperFetchError
from scrapers.indiegogo import IndiegogoScraper


def _record(**updates):
    value = {
        "projectId": 123,
        "projectName": "Compact Travel Organizer",
        "shortDescription": "A lightweight organizer for travel accessories.",
        "projectHomeUrl": "https://www.indiegogo.com/projects/compact-organizer",
        "projectImageUrl": "https://example.com/organizer.jpg",
        "campaignGoal": 10000,
        "fundsGathered": 15000,
        "backerCount": 250,
        "currencyShortName": "USD",
        "campaignStartDate": "2026-08-01T00:00:00Z",
        "campaignEndDate": "2026-09-01T00:00:00Z",
        "creatorName": "Example Creator",
        "commentCount": 12,
    }
    value.update(updates)
    return value


def test_indiegogo_maps_public_fields_and_funding_percentage(monkeypatch):
    scraper = IndiegogoScraper()
    monkeypatch.setattr(scraper, "_fetch_bytes", lambda: json.dumps([_record()]).encode())
    product = scraper.fetch()[0]
    assert product.source_platform == "indiegogo"
    assert product.title == "Compact Travel Organizer"
    assert product.raw_data["funding_percentage"] == 150
    assert product.raw_data["backer_count"] == 250
    assert product.raw_data["fetched_at"]


def test_indiegogo_skips_bad_record_without_losing_good_one(monkeypatch):
    scraper = IndiegogoScraper()
    payload = [{"projectName": "bad"}, _record()]
    monkeypatch.setattr(scraper, "_fetch_bytes", lambda: json.dumps(payload).encode())
    assert len(scraper.fetch()) == 1


def test_indiegogo_network_error_is_explicit(monkeypatch):
    scraper = IndiegogoScraper()
    def fail(*_args, **_kwargs):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(ScraperFetchError, match="HTTP status: unavailable"):
        scraper.fetch()
