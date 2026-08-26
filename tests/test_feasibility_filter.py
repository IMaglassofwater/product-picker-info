"""Tests for the personal seller feasibility pre-filter."""

import pytest

from feasibility_filter import FeasibilityResult, filter_feasibility
from models import Product


def _product(title: str, description: str, raw_data: dict | None = None) -> Product:
    return Product(
        project_id="feasibility-1",
        source_platform="kickstarter",
        url="https://example.com/feasibility-product",
        title=title,
        description=description,
        category="Product Design",
        image_url="https://example.com/feasibility-product.jpg",
        raw_data=raw_data or {},
    )


@pytest.mark.parametrize(
    ("title", "description", "expected_risks"),
    [
        (
            "Adventure Mate 6-in-1",
            "Axe, saw, shovel and hook for camping",
            {"weapon_or_blade"},
        ),
        (
            "21-in-1 Titanium Multi-Tool",
            "Built around an M390 blade",
            {"weapon_or_blade"},
        ),
        (
            "AI panoramic camera",
            "Four lens system with Bluetooth and AI tracking",
            {"complex_electronics", "wireless"},
        ),
        (
            "Wireless mechanical keyboard",
            "Bluetooth and 2.4G connectivity",
            {"complex_electronics", "wireless"},
        ),
        (
            "Power Bank",
            "Battery system with wireless charging",
            {"complex_electronics", "wireless"},
        ),
    ],
)
def test_hard_risk_products_are_rejected(title, description, expected_risks):
    result = filter_feasibility(_product(title, description))

    assert isinstance(result, FeasibilityResult)
    assert result.feasibility_status == "REJECT"
    assert expected_risks.issubset(result.risk_flags)


@pytest.mark.parametrize(
    ("title", "description"),
    [
        (
            "Simple desktop organizer",
            "Compact non-electronic ABS cable and storage organization",
        ),
        (
            "Travel cable organizer pouch",
            "Lightweight polyester non-electronic travel organizer",
        ),
        (
            "Simple pet accessory",
            "Non-electronic lightweight product with simple structure",
        ),
    ],
)
def test_simple_low_tech_products_pass(title, description):
    result = filter_feasibility(_product(title, description))

    assert result.feasibility_status == "PASS"
    assert result.feasibility_score >= 60
    assert result.risk_flags == []


def test_unknown_passive_cooling_accessory_requires_review():
    result = filter_feasibility(
        _product(
            "Novel passive cooling accessory",
            "Compact and requires no electricity, but manufacturing is unknown",
        )
    )

    assert result.feasibility_status == "REVIEW"


def test_market_success_does_not_override_hardware_rejection():
    result = filter_feasibility(
        _product(
            "AI panoramic camera",
            "Four lens AI tracking camera with Bluetooth",
            raw_data={"percent_funded": 10000, "backers_count": 5000},
        )
    )

    assert result.feasibility_status == "REJECT"
    assert "complex_electronics" in result.risk_flags
    assert "wireless" in result.risk_flags


@pytest.mark.parametrize(
    ("title", "description"),
    [
        (
            "Mac Mini Dock",
            "14-in-1 Thunderbolt dock with 8TB SSD storage",
        ),
        ("Portable 20Gbps SSD", "High-speed storage drive"),
        (
            "Battery Hub",
            "Fast charging electronics with battery health check",
        ),
    ],
)
def test_complex_storage_and_charging_electronics_are_rejected(title, description):
    result = filter_feasibility(_product(title, description))

    assert result.feasibility_status == "REJECT"
    assert "complex_electronics" in result.risk_flags


def test_simple_key_organizer_passes():
    result = filter_feasibility(
        _product(
            "Simple key organizer",
            "Small non-electronic everyday accessory",
        )
    )

    assert result.feasibility_status == "PASS"


def test_simple_backpack_is_pass_or_review():
    result = filter_feasibility(
        _product("Simple backpack", "Recycled nylon 13L backpack")
    )

    assert result.feasibility_status in {"PASS", "REVIEW"}


def test_multifunction_ruler_remains_review():
    result = filter_feasibility(
        _product("OMNI-R multifunction ruler", "12 measurement features")
    )

    assert result.feasibility_status == "REVIEW"


@pytest.mark.parametrize(
    ("title", "description"),
    [
        (
            "Simple key organizer",
            "Small non-electronic product with simple structure made from ABS",
        ),
        (
            "Travel cable organizer pouch",
            "Polyester, lightweight, compact and non-electronic",
        ),
        (
            "13L recycled nylon everyday backpack",
            "Simple laptop sleeve and non-electronic construction",
        ),
        (
            "Simple desk organizer",
            "Compact non-electronic ABS accessory",
        ),
        (
            "Simple pet accessory",
            "Small non-electronic nylon product",
        ),
    ],
)
def test_clear_simple_consumer_products_pass(title, description):
    result = filter_feasibility(_product(title, description))

    assert result.feasibility_status == "PASS"
    assert result.feasibility_score >= 70
    assert len(result.positive_signals) >= 4


@pytest.mark.parametrize(
    ("title", "description"),
    [
        ("Titanium EDC wallet", "GR5 titanium with a special mechanism"),
        ("Titanium serving tray", "A modular titanium serving tray"),
    ],
)
def test_special_material_products_require_review(title, description):
    result = filter_feasibility(_product(title, description))

    assert result.feasibility_status == "REVIEW"
    assert result.feasibility_score < 70


def test_extreme_funding_does_not_override_complex_electronics():
    result = filter_feasibility(
        _product(
            "Smart battery hub",
            "Battery health check and fast charging electronics",
            raw_data={"funding_percentage": 20000},
        )
    )

    assert result.feasibility_status == "REJECT"
    assert "complex_electronics" in result.risk_flags
