"""Tests for demand productization feasibility pre-filtering."""

import pytest

from demand_opportunity_filter import filter_demand_opportunity
from demand_signal_filter import DemandSignalResult
from models import Product


def _evaluate(title: str, description: str):
    product = Product(
        project_id="opportunity-1",
        source_platform="reddit_arctic_shift",
        url="https://example.com/opportunity-1",
        title=title,
        description=description,
        category="EDC",
        image_url="https://example.com/opportunity-1.jpg",
        raw_data={},
    )
    signal = DemandSignalResult(
        signal_status="HIGH",
        signal_score=90,
        signal_type="purchase_intent",
        reason="test demand",
    )
    return filter_demand_opportunity(product, signal)


def test_zipper_free_fanny_pack_is_productizable():
    result = _evaluate(
        "Fanny pack without zipper",
        "A work pouch for quick access to items I reach for often",
    )

    assert result.demand_opportunity_status == "PRODUCTIZABLE"
    assert {
        "existing_simple_product", "clear_feature_gap",
        "accessibility_problem", "low_tech_modification",
    }.issubset(result.opportunity_flags)


def test_professional_work_backpack_is_productizable():
    result = _evaluate(
        "Professional work backpack, not hiking or tactical",
        "For daily work with laptop organization and discreet EDC storage",
    )

    assert result.demand_opportunity_status == "PRODUCTIZABLE"
    assert {
        "appearance_positioning_gap", "clear_usage_scenario",
        "existing_simple_product",
    }.issubset(result.opportunity_flags)


def test_crossbody_with_dimensions_is_productizable():
    result = _evaluate(
        "Crossbody bag with specific requirements",
        "Waist strap >44 inches and specific EDC storage compartments",
    )

    assert result.demand_opportunity_status == "PRODUCTIZABLE"
    assert {
        "clear_size_requirement", "clear_feature_gap",
        "existing_simple_product",
    }.issubset(result.opportunity_flags)


def test_key_organizer_gap_is_productizable():
    result = _evaluate(
        "Key organizer",
        "Works with flat and rounded keys and holds up to 10 keys",
    )

    assert result.demand_opportunity_status == "PRODUCTIZABLE"


@pytest.mark.parametrize(
    ("title", "description", "risk"),
    [
        ("Refrigerator under budget", "Need a 600L refrigerator", "large_or_heavy_product"),
        ("Battery backup for car refrigerator", "Need a battery source for a car fridge", "complex_electronics"),
    ],
)
def test_hard_resource_mismatches_are_not_fit(title, description, risk):
    result = _evaluate(title, description)

    assert result.demand_opportunity_status == "NOT_FIT"
    assert risk in result.demand_opportunity_reason


@pytest.mark.parametrize(
    ("title", "description"),
    [
        ("Durable technical running shoes", "Need high-performance trail footwear"),
        ("Tent recommendation", "Lightweight tent for a dog with more space"),
        ("Help optimize my onebag setup", "Need advice across my complete packing list"),
    ],
)
def test_complex_or_multi_product_demands_require_review(title, description):
    result = _evaluate(title, description)

    assert result.demand_opportunity_status == "REVIEW"


def test_price_pain_diy_journal_is_productizable():
    result = _evaluate(
        "Leather journal",
        "The existing journal was too expensive, so I made one myself",
    )

    assert result.demand_opportunity_status == "PRODUCTIZABLE"
    assert {
        "clear_price_pain", "DIY_workaround", "existing_simple_product",
    }.issubset(result.opportunity_flags)
