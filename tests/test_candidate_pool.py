"""Tests for the unified micro-innovation candidate pool."""

import sqlite3

import db
from candidate_pool import (
    build_consumer_trend_candidate,
    build_demand_candidate,
    build_inspiration_candidate,
    build_validated_product_candidate,
    deduplicate_candidates,
)
from creative_content_filter import filter_creative_content
from demand_opportunity_filter import filter_demand_opportunity
from demand_signal_filter import DemandSignalResult
from feasibility_filter import filter_feasibility
from models import Product


def _product(
    title: str,
    description: str,
    *,
    source: str = "reddit_arctic_shift",
    url: str = "https://example.com/candidate",
    raw_data: dict | None = None,
) -> Product:
    return Product(
        project_id="candidate-source-1",
        source_platform=source,
        url=url,
        title=title,
        description=description,
        category="EDC",
        image_url="https://example.com/candidate.jpg",
        raw_data=raw_data or {},
    )


def _demand_candidate(product: Product):
    signal = DemandSignalResult("HIGH", 90, "purchase_intent", "test")
    opportunity = filter_demand_opportunity(product, signal)
    return build_demand_candidate(
        product,
        demand_opportunity_status=opportunity.demand_opportunity_status,
        demand_opportunity_score=opportunity.demand_opportunity_score,
        signal_score=signal.signal_score,
        signal_type=signal.signal_type,
        opportunity_flags=opportunity.opportunity_flags,
    )


def test_zipper_free_fanny_pack_has_high_micro_innovation_score():
    candidate = _demand_candidate(
        _product(
            "Zipper-free fanny pack",
            "Work pouch without a zipper for quick access to daily items",
        )
    )

    assert candidate is not None
    assert candidate.candidate_type == "demand_opportunity"
    assert candidate.micro_innovation_score >= 70


def test_professional_work_backpack_becomes_demand_candidate():
    candidate = _demand_candidate(
        _product(
            "Professional non-tactical work backpack",
            "Daily laptop organization and easy-access EDC storage",
        )
    )

    assert candidate is not None


def test_key_organizer_has_high_candidate_score():
    candidate = _demand_candidate(
        _product(
            "Key organizer",
            "For flat + rounded keys and holds up to 10 keys",
        )
    )

    assert candidate is not None
    assert candidate.candidate_score >= 70


def test_refrigerator_not_fit_does_not_enter_pool():
    assert _demand_candidate(
        _product("Refrigerator under budget", "Need a durable 600L refrigerator")
    ) is None


def test_rejected_complex_kickstarter_product_does_not_enter_pool():
    product = _product(
        "Smart battery hub",
        "Fast charging electronics with Bluetooth",
        source="kickstarter",
    )
    feasibility = filter_feasibility(product)

    candidate = build_validated_product_candidate(
        product,
        feasibility_status=feasibility.feasibility_status,
        feasibility_score=feasibility.feasibility_score,
        positive_signals=feasibility.positive_signals,
    )

    assert feasibility.feasibility_status == "REJECT"
    assert candidate is None


def test_simple_validated_kickstarter_product_enters_pool():
    product = _product(
        "Simple travel organizer pouch",
        "Compact lightweight non-electronic polyester pouch with simple structure",
        source="kickstarter",
        raw_data={"backers_count": 1200, "percent_funded": 450},
    )
    feasibility = filter_feasibility(product)

    candidate = build_validated_product_candidate(
        product,
        feasibility_status=feasibility.feasibility_status,
        feasibility_score=feasibility.feasibility_score,
        positive_signals=feasibility.positive_signals,
    )

    assert feasibility.feasibility_status == "PASS"
    assert candidate is not None
    assert candidate.candidate_type == "validated_product"
    assert candidate.market_validation_score > 0


def test_duplicate_source_url_is_not_created_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "candidate.db")
    product = _product(
        "Key organizer",
        "For flat + rounded keys and holds up to 10 keys",
    )
    candidate = _demand_candidate(product)
    assert candidate is not None

    unique = deduplicate_candidates([candidate, candidate])
    saved, duplicates = db.save_candidates([candidate, candidate])

    assert len(unique) == 1
    assert (saved, duplicates) == (1, 1)
    with sqlite3.connect(db.DB_PATH) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM micro_innovation_candidates"
        ).fetchone()[0]
    assert count == 1


def test_inspiration_candidate_uses_required_score_weights():
    product = _product(
        "Compact modular desk organizer",
        "A simple non-electronic modular storage organizer for everyday desk use",
        source="yanko_design",
        raw_data={
            "categories": ["Product Design", "Accessories"],
            "published_at": "2026-08-25",
            "image_url": "https://example.com/candidate.jpg",
        },
    )
    result = filter_creative_content(product)
    candidate = build_inspiration_candidate(product, result)

    assert candidate is not None
    assert candidate.candidate_score == round(
        0.45 * result.feasibility_score
        + 0.40 * result.micro_innovation_score
        + 0.15 * result.information_clarity_score
    )
    assert candidate.market_validation_score == 0


def test_consumer_trend_candidate_uses_required_score_weights():
    product = _product(
        "Compact storage tray", "Simple lightweight organizer",
        source="amazon", raw_data={"source_list": "new_releases", "rank": 4},
    )
    candidate = build_consumer_trend_candidate(
        product, status="candidate", feasibility_score=70,
        market_signal_score=80, micro_innovation_score=60,
        signals=["simple_physical", "new_release_signal"],
        reason="public trend signal; no sales claim",
        commodity_status="PROMISING",
    )
    assert candidate is not None
    assert candidate.candidate_type == "consumer_trend"
    assert candidate.candidate_score == round(0.40 * 70 + 0.35 * 80 + 0.25 * 60)


def test_non_candidate_amazon_item_does_not_enter_pool():
    assert build_consumer_trend_candidate(
        _product("Wireless camera", "Electronic", source="amazon"),
        status="rejected", feasibility_score=20, market_signal_score=80,
        micro_innovation_score=10, signals=[], reason="complex",
        commodity_status="COMMODITY",
    ) is None


def test_review_consumer_trend_does_not_enter_high_priority_pool():
    assert build_consumer_trend_candidate(
        _product("Basic tumbler", "Insulated cup", source="amazon"),
        status="candidate", feasibility_score=70, market_signal_score=90,
        micro_innovation_score=55, signals=["simple_physical"],
        reason="market signal only", commodity_status="REVIEW",
    ) is None
