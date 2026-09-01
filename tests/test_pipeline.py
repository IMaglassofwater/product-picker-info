"""Tests for the bounded multi-source Product Picker pipeline."""

import sqlite3

import db
import main
from models import Product
from scrapers.base_scraper import ScraperFetchError


def _product(
    source_platform: str,
    index: int,
    *,
    title: str = "Simple item",
    raw_data: dict | None = None,
) -> Product:
    return Product(
        project_id=f"{source_platform}-{index}",
        source_platform=source_platform,
        url=f"https://example.com/{source_platform}/{index}",
        title=title,
        description="A mock product used by the pipeline tests",
        category="General",
        image_url=f"https://example.com/images/{source_platform}-{index}.jpg",
        raw_data=raw_data or {},
    )


class _MockScraper:
    def __init__(self, source_name: str, products: list[Product]) -> None:
        self.source_name = source_name
        self.products = products

    def fetch(self) -> list[Product]:
        return self.products


class _FailingScraper:
    def __init__(self, source_name: str) -> None:
        self.source_name = source_name

    def fetch(self) -> list[Product]:
        raise ScraperFetchError(f"{self.source_name} mock failure")


def _three_scrapers() -> list[_MockScraper]:
    return [
        _MockScraper("product_hunt", [_product("product_hunt", 1)]),
        _MockScraper(
            "kickstarter",
            [
                _product(
                    "kickstarter",
                    1,
                    title="Compact EDC organizer tool",
                    raw_data={"percent_funded": 150, "backers_count": 100},
                )
            ],
        ),
        _MockScraper(
            "reddit_arctic_shift",
            [
                _product(
                    "reddit_arctic_shift",
                    1,
                    raw_data={"score": 20, "num_comments": 5},
                )
            ],
        ),
    ]


def test_three_scrapers_enter_unified_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    messages: list[str] = []

    assert main.run_pipeline(
        scrapers=_three_scrapers(), output=messages.append
    ) is True

    output = "\n".join(messages)
    assert "Product Hunt" in output
    assert "Kickstarter / KSInsights" in output
    assert "Reddit / Arctic Shift" in output
    assert "Total fetched:\n3" in output
    assert "Total processed:\n3" in output
    assert {product.source_platform for product in db.get_all_products()} == {
        "product_hunt",
        "kickstarter",
        "reddit_arctic_shift",
    }


def test_ksinsights_failure_does_not_stop_other_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    messages: list[str] = []
    scrapers = [
        _MockScraper("product_hunt", [_product("product_hunt", 1)]),
        _FailingScraper("kickstarter"),
        _MockScraper(
            "reddit_arctic_shift", [_product("reddit_arctic_shift", 1)]
        ),
    ]

    assert main.run_pipeline(scrapers=scrapers, output=messages.append) is True

    output = "\n".join(messages)
    assert "kickstarter mock failure" in output
    assert "Total processed:\n2" in output
    assert "Saved:\n2" in output
    with sqlite3.connect(db.DB_PATH) as connection:
        failed, error = connection.execute(
            "SELECT failed, error FROM pipeline_source_runs WHERE source_platform='kickstarter'"
        ).fetchone()
    assert failed == 1 and "mock failure" in error


def test_arctic_shift_failure_does_not_stop_other_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    messages: list[str] = []
    scrapers = [
        _MockScraper("product_hunt", [_product("product_hunt", 1)]),
        _MockScraper("kickstarter", [_product("kickstarter", 1)]),
        _FailingScraper("reddit_arctic_shift"),
    ]

    assert main.run_pipeline(scrapers=scrapers, output=messages.append) is True

    output = "\n".join(messages)
    assert "reddit_arctic_shift mock failure" in output
    assert "Total processed:\n2" in output
    assert "Saved:\n2" in output


def test_phase11e_source_failure_does_not_stop_other_new_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    messages: list[str] = []
    scrapers = [
        _FailingScraper("etsy"),
        _MockScraper(
            "hacker_news",
            [_product("hacker_news", 1, title="Show HN: TidyCSV tool")],
        ),
    ]
    assert main.run_pipeline(scrapers=scrapers, output=messages.append) is True
    output = "\n".join(messages)
    assert "etsy mock failure" in output
    assert "Total processed:\n1" in output
    assert db.get_all_products()[0].source_platform == "hacker_news"


def test_deferred_design_milk_does_not_block_software_reddit(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    messages: list[str] = []
    scrapers = [
        _FailingScraper("design_milk"),
        _MockScraper(
            "reddit_software",
            [_product("reddit_software", 1, title="Local-first expense tracker app")],
        ),
    ]
    assert main.run_pipeline(scrapers=scrapers, output=messages.append) is True
    assert "design_milk mock failure" in "\n".join(messages)
    assert db.get_all_products()[0].source_platform == "reddit_software"


def test_max_items_per_source_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    messages: list[str] = []
    scrapers = [
        _MockScraper(
            "product_hunt",
            [_product("product_hunt", index) for index in range(51)],
        ),
        _MockScraper(
            "kickstarter",
            [_product("kickstarter", index) for index in range(101)],
        ),
        _MockScraper(
            "reddit_arctic_shift",
            [_product("reddit_arctic_shift", index) for index in range(181)],
        ),
    ]

    assert main.run_pipeline(scrapers=scrapers, output=messages.append) is True

    output = "\n".join(messages)
    assert "Total fetched:\n333" in output
    assert "Total processed:\n330" in output
    assert len(db.get_all_products()) == 330


def test_funded_project_gets_market_validation_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    product = _product(
        "kickstarter", 1, raw_data={"percent_funded": 150, "backers_count": 10}
    )
    messages: list[str] = []

    main.run_pipeline(
        scrapers=[_MockScraper("kickstarter", [product])],
        output=messages.append,
    )

    with sqlite3.connect(db.DB_PATH) as connection:
        reason = connection.execute(
            "SELECT filter_reason FROM products WHERE url = ?", (product.url,)
        ).fetchone()[0]
    assert "market validated: funded >= 100%" in reason
    assert "Kickstarter funded >=100%:\n1" in "\n".join(messages)


def test_high_funding_keeps_only_basic_market_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    product = _product(
        "kickstarter", 1, raw_data={"percent_funded": 350, "backers_count": 25}
    )
    messages: list[str] = []

    main.run_pipeline(
        scrapers=[_MockScraper("kickstarter", [product])],
        output=messages.append,
    )

    with sqlite3.connect(db.DB_PATH) as connection:
        reason = connection.execute(
            "SELECT filter_reason FROM products WHERE url = ?", (product.url,)
        ).fetchone()[0]
    assert "market validated: funded >= 100%" in reason
    assert "strong crowdfunding validation" not in reason
    output = "\n".join(messages)
    assert "Kickstarter funded >=300%" not in output


def test_pipeline_persists_feasibility_result(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    product = _product(
        "kickstarter",
        1,
        title="Simple desktop organizer",
        raw_data={"percent_funded": 500},
    )
    product.description = "Compact non-electronic ABS cable storage organizer"
    product.category = "Desk accessory"
    messages: list[str] = []

    main.run_pipeline(
        scrapers=[_MockScraper("kickstarter", [product])],
        output=messages.append,
    )

    with sqlite3.connect(db.DB_PATH) as connection:
        row = connection.execute(
            """
            SELECT feasibility_status, feasibility_score, risk_flags,
                   positive_signals
            FROM products WHERE url = ?
            """,
            (product.url,),
        ).fetchone()
    assert row[0] == "PASS"
    assert row[1] >= 60
    assert row[2] == "[]"
    assert "common_consumer_category" in row[3]
    output = "\n".join(messages)
    assert "PASS:\n1" in output
    assert "Feasible Physical Candidates:\n1" in output


def test_existing_url_is_not_saved_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    scraper = _MockScraper("product_hunt", [_product("product_hunt", 1)])

    main.run_pipeline(scrapers=[scraper], output=lambda _message: None)
    messages: list[str] = []
    main.run_pipeline(scrapers=[scraper], output=messages.append)

    output = "\n".join(messages)
    assert "Saved:\n0" in output
    assert "Duplicates:\n1" in output
    assert len(db.get_all_products()) == 1


def test_pipeline_routes_demand_signal_without_feasibility(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    product = _product(
        "reddit_arctic_shift",
        9,
        title="Looking for key organiser",
    )
    product.description = "Works with flat and rounded keys; holds up to ten keys"
    messages: list[str] = []

    main.run_pipeline(
        scrapers=[_MockScraper("reddit_arctic_shift", [product])],
        output=messages.append,
    )

    with sqlite3.connect(db.DB_PATH) as connection:
        row = connection.execute(
            """
            SELECT record_role, feasibility_status, demand_signal_status,
                   demand_signal_type, demand_opportunity_status,
                   opportunity_flags
            FROM products WHERE url = ?
            """,
            (product.url,),
        ).fetchone()
    assert row[0] == "demand_signal"
    assert row[1] == ""
    assert row[2] == "HIGH"
    assert row[3] in {"purchase_intent", "product_gap"}
    assert row[4] == "PRODUCTIZABLE"
    assert "existing_simple_product" in row[5]
    output = "\n".join(messages)
    assert "Demand Signals:\n1" in output
    assert "HIGH:\n1" in output
    assert "Demand Opportunity Candidates:\n1" in output
    with sqlite3.connect(db.DB_PATH) as connection:
        candidate_count = connection.execute(
            "SELECT COUNT(*) FROM micro_innovation_candidates"
        ).fetchone()[0]
    assert candidate_count == 1


def test_isolated_yanko_validation_builds_only_inspiration_candidates(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    product = _product(
        "yanko_design",
        1,
        title="Compact modular travel pouch",
        raw_data={
            "categories": ["Product Design", "Accessories"],
            "tags": ["Product Design", "Accessories"],
            "published_at": "2026-08-25",
            "image_url": "https://example.com/1.jpg",
        },
    )
    product.description = (
        "A simple non-electronic fabric pouch with modular storage pockets "
        "for daily travel"
    )
    messages: list[str] = []

    assert main.run_yanko_validation(
        scraper=_MockScraper("yanko_design", [product]),
        output=messages.append,
    ) is True

    candidates = db.get_all_candidates()
    assert len(candidates) == 1
    assert candidates[0].candidate_type == "inspiration_product"
    assert "Inspiration Candidates:\n1" in "\n".join(messages)


def test_isolated_amazon_validation_builds_consumer_trend_candidate(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    product = _product("amazon", 1, title="Modular foldable desk organizer tray")
    product.category = "Home & Kitchen"
    product.description = product.title
    product.raw_data = {
        "asin": "B0ABC12345", "rank": 2, "rank_change": None,
        "price": "$12.99", "rating": 4.5, "review_count": 40,
        "category": product.category, "image_url": product.image_url,
        "source_list": "new_releases",
    }
    messages = []
    assert main.run_amazon_validation(
        scraper=_MockScraper("amazon", [product]), output=messages.append
    ) is True
    assert db.get_all_candidates()[0].candidate_type == "consumer_trend"
    assert "Consumer Trend Candidates:\n1" in "\n".join(messages)


def test_amazon_commodity_reprocess_keeps_only_promising(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    promising = _product("amazon", 1, title="Modular foldable organizer tray")
    commodity = _product("amazon", 2, title="Basic bathroom rug bath mat")
    for product in (promising, commodity):
        product.category = "Home & Kitchen"
        product.description = product.title
        product.raw_data = {"source_list": "new_releases", "rank": 2}
    main.run_amazon_validation(
        scraper=_MockScraper("amazon", [promising, commodity]),
        output=lambda _message: None,
    )
    from candidate_pool import build_consumer_trend_candidate
    legacy_commodity_candidate = build_consumer_trend_candidate(
        commodity, status="candidate", feasibility_score=70,
        market_signal_score=70, micro_innovation_score=55,
        signals=["simple_physical"], reason="legacy Phase 7.4C candidate",
        commodity_status="PROMISING",
    )
    assert legacy_commodity_candidate is not None
    db.save_candidates([legacy_commodity_candidate])
    messages = []
    assert main.run_amazon_commodity_reprocess(output=messages.append) is True
    assert [item.title for item in db.get_all_candidates()] == [promising.title]
    output = "\n".join(messages)
    assert "PROMISING:\n1" in output
    assert "COMMODITY:\n1" in output


def test_amazon_failure_is_optional_and_does_not_fail_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "product_picker.db")
    messages = []
    assert main.run_amazon_validation(
        scraper=_FailingScraper("amazon"), output=messages.append
    ) is True
    assert "Pipeline continued without Amazon." in "\n".join(messages)


def test_core_and_phase_11e_sources_are_in_default_pipeline():
    assert {scraper.source_name for scraper in main.SCRAPERS} == {
        "reddit_arctic_shift", "amazon", "kickstarter", "indiegogo",
        "yanko_design", "product_hunt", "etsy", "hacker_news",
        "reddit_software", "design_milk",
    }
