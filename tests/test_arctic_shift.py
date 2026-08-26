"""Tests for the third-party Arctic Shift historical Reddit adapter."""

import io
import json
import urllib.error
import urllib.parse

import pytest

from models import Product
from config import (
    REDDIT_INTENTS,
    REDDIT_INTENT_QUERY_BATCHES,
    REDDIT_SUBREDDIT_INTENTS,
    REDDIT_SUBREDDITS,
)
from scrapers.arctic_shift import ArcticShiftScraper
from scrapers.base_scraper import ScraperFetchError


MOCK_RESPONSE = {
    "data": [
        {
            "id": "abc123",
            "title": "Compact EDC organizer",
            "selftext": "A small organizer for everyday tools.",
            "subreddit": "EDC",
            "permalink": "/r/EDC/comments/abc123/compact_edc_organizer/",
            "score": 125,
            "num_comments": 24,
            "created_utc": 1760000000,
            "author": "example_user",
        }
    ]
}


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._buffer = io.BytesIO(payload)

    def read(self) -> bytes:
        return self._buffer.read()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_arctic_shift_product_mapping(monkeypatch):
    scraper = ArcticShiftScraper(subreddits=["EDC"], limit_per_subreddit=5)
    payload = json.dumps(MOCK_RESPONSE).encode("utf-8")
    monkeypatch.setattr(
        "scrapers.arctic_shift.urllib.request.urlopen",
        lambda _request, timeout: _Response(payload),
    )

    product = scraper.fetch()[0]

    assert isinstance(product, Product)
    assert product.project_id == "abc123"
    assert product.source_platform == "reddit_arctic_shift"
    assert product.category == "EDC"
    assert product.url.startswith("https://www.reddit.com/r/EDC/")


def test_arctic_shift_metrics_are_preserved(monkeypatch):
    scraper = ArcticShiftScraper(subreddits=["EDC"])
    payload = json.dumps(MOCK_RESPONSE).encode("utf-8")
    monkeypatch.setattr(
        "scrapers.arctic_shift.urllib.request.urlopen",
        lambda _request, timeout: _Response(payload),
    )

    raw_data = scraper.fetch()[0].raw_data

    assert raw_data["score"] == 125
    assert raw_data["num_comments"] == 24
    assert raw_data["subreddit"] == "EDC"
    assert raw_data["retrieval_source"] == "arctic_shift"


def test_arctic_shift_network_failure(monkeypatch):
    scraper = ArcticShiftScraper(subreddits=["EDC"])

    def fail(_request, timeout):
        assert timeout == scraper.REQUEST_TIMEOUT
        raise urllib.error.URLError("historical service unavailable")

    monkeypatch.setattr("scrapers.arctic_shift.urllib.request.urlopen", fail)

    with pytest.raises(ScraperFetchError) as error:
        scraper.fetch()

    assert "historical service unavailable" in str(error.value)


def _record(subreddit: str, index: int, url: str | None = None) -> dict:
    return {
        "id": f"{subreddit}-{index}",
        "title": f"Looking for {subreddit} item {index}",
        "selftext": f"Description from {subreddit}",
        "subreddit": subreddit,
        "permalink": url or f"/r/{subreddit}/comments/{index}/post/",
        "score": index,
        "num_comments": index + 1,
        "created_utc": 1760000000,
        "author": "example_user",
    }


def test_default_configuration_contains_all_communities():
    scraper = ArcticShiftScraper()

    assert scraper.subreddits == tuple(item["name"] for item in REDDIT_SUBREDDITS)
    assert scraper.limit_per_subreddit == 30
    assert "looking for" in REDDIT_INTENTS
    assert "lightweight" in REDDIT_SUBREDDIT_INTENTS["onebag"]


def test_each_subreddit_is_requested_independently(monkeypatch):
    requested: list[str] = []

    def respond(request, timeout):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
        subreddit = query["subreddit"][0]
        requested.append(subreddit)
        assert "after" in query
        payload = json.dumps({"data": [_record(subreddit, 1)]}).encode()
        return _Response(payload)

    monkeypatch.setattr("scrapers.arctic_shift.urllib.request.urlopen", respond)
    scraper = ArcticShiftScraper(subreddits=["EDC", "onebag"])

    products = scraper.fetch()

    assert requested == ["EDC", "EDC", "onebag", "onebag"]
    assert {product.category for product in products} == {"EDC", "onebag"}
    assert scraper.fetch_counts == {"EDC": 1, "onebag": 1}


def test_one_subreddit_failure_does_not_stop_others(monkeypatch):
    def respond(request, timeout):
        subreddit = urllib.parse.parse_qs(
            urllib.parse.urlparse(request.full_url).query
        )["subreddit"][0]
        if subreddit == "onebag":
            raise urllib.error.URLError("onebag timeout")
        return _Response(json.dumps({"data": [_record(subreddit, 1)]}).encode())

    monkeypatch.setattr("scrapers.arctic_shift.urllib.request.urlopen", respond)
    scraper = ArcticShiftScraper(subreddits=["onebag", "BuyItForLife"])

    products = scraper.fetch()

    assert [product.category for product in products] == ["BuyItForLife"]
    assert "onebag" in scraper.failures
    assert scraper.fetch_counts["onebag"] == 0


def test_per_community_limit_is_enforced(monkeypatch):
    payload = json.dumps(
        {"data": [_record("EDC", index) for index in range(8)]}
    ).encode()
    monkeypatch.setattr(
        "scrapers.arctic_shift.urllib.request.urlopen",
        lambda _request, timeout: _Response(payload),
    )
    scraper = ArcticShiftScraper(subreddits=["EDC"], limit_per_subreddit=3)

    assert len(scraper.fetch()) == 3
    assert scraper.fetch_counts["EDC"] == 3


def test_duplicate_post_url_is_returned_once(monkeypatch):
    shared_url = "/r/EDC/comments/shared/post/"

    def respond(request, timeout):
        subreddit = urllib.parse.parse_qs(
            urllib.parse.urlparse(request.full_url).query
        )["subreddit"][0]
        record = _record(subreddit, 1, shared_url)
        return _Response(json.dumps({"data": [record]}).encode())

    monkeypatch.setattr("scrapers.arctic_shift.urllib.request.urlopen", respond)
    scraper = ArcticShiftScraper(subreddits=["EDC", "onebag"])

    products = scraper.fetch()

    assert len(products) == 1
    assert products[0].category == "EDC"


def test_subreddit_uses_two_configured_intent_queries():
    scraper = ArcticShiftScraper(subreddits=["onebag"])

    batches = scraper._intent_batches("onebag")

    assert len(batches) == 2
    assert batches == REDDIT_INTENT_QUERY_BATCHES["onebag"]
    assert set(batches).issubset(REDDIT_SUBREDDIT_INTENTS["onebag"])


def test_removed_post_is_skipped(monkeypatch):
    records = [
        {**_record("EDC", 1), "selftext": "[removed]"},
        _record("EDC", 2),
    ]
    monkeypatch.setattr(
        "scrapers.arctic_shift.urllib.request.urlopen",
        lambda _request, timeout: _Response(json.dumps({"data": records}).encode()),
    )
    scraper = ArcticShiftScraper(subreddits=["EDC"])

    products = scraper.fetch()

    assert len(products) == 1
    assert products[0].project_id == "EDC-2"
    assert scraper.invalid_counts["EDC"] == 2


def test_matched_intents_and_source_are_preserved(monkeypatch):
    record = _record("onebag", 1)
    record["title"] = "Looking for a lightweight pack"
    payload = json.dumps({"data": [record]}).encode()
    monkeypatch.setattr(
        "scrapers.arctic_shift.urllib.request.urlopen",
        lambda _request, timeout: _Response(payload),
    )
    scraper = ArcticShiftScraper(subreddits=["onebag"])

    raw_data = scraper.fetch()[0].raw_data

    assert {"looking for", "lightweight", "pack"}.issubset(
        raw_data["matched_intents"]
    )
    assert raw_data["intent_source"] == "onebag"


def test_one_query_failure_does_not_stop_second_query(monkeypatch):
    calls = 0

    def respond(_request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.URLError("first intent batch timeout")
        return _Response(
            json.dumps({"data": [_record("EDC", 1)]}).encode()
        )

    monkeypatch.setattr("scrapers.arctic_shift.urllib.request.urlopen", respond)
    scraper = ArcticShiftScraper(subreddits=["EDC"])

    products = scraper.fetch()

    assert len(products) == 1
    assert calls == 2
    assert "EDC" not in scraper.failures
    assert len(scraper.query_failures["EDC"]) == 1
