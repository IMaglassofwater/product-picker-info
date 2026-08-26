"""Tests for source-aware role routing and Reddit demand signals."""

from demand_signal_filter import classify_record_role, filter_demand_signal
from models import Product
from rule_filter import filter_product


def _product(title: str, description: str, source: str = "reddit_arctic_shift") -> Product:
    return Product(
        project_id="signal-1",
        source_platform=source,
        url="https://example.com/signal-1",
        title=title,
        description=description,
        category="EDC",
        image_url="https://example.com/signal-1.jpg",
        raw_data={},
    )


def _role(product: Product) -> str:
    opportunity = filter_product(product).opportunity_type
    return classify_record_role(product, opportunity).record_role


def test_key_organiser_is_high_demand_signal():
    product = _product(
        "Looking for key organiser",
        "Needs to work with flat and rounded keys and holds up to ten keys",
    )

    result = filter_demand_signal(product)

    assert _role(product) == "demand_signal"
    assert result.signal_type in {"purchase_intent", "product_gap"}
    assert result.signal_status == "HIGH"


def test_price_pain_and_diy_workaround_are_preserved():
    product = _product(
        "Leather journal",
        "PaperRepublic was too expensive, so I made one myself",
    )

    result = filter_demand_signal(product)

    assert _role(product) == "demand_signal"
    assert result.signal_type == "price_pain"
    assert "DIY_workaround" in result.reason
    assert result.signal_status == "HIGH"


def test_suggestion_request_is_demand_signal():
    product = _product(
        "Considering adding an EDC item, taking suggestions",
        "What should I get for the office and dog walking?",
    )

    result = filter_demand_signal(product)

    assert _role(product) == "demand_signal"
    assert result.signal_type == "recommendation_request"
    assert result.signal_status == "HIGH"


def test_reddit_concrete_backpack_is_not_automatically_demand():
    product = _product(
        "Simple backpack",
        "A recycled nylon 13L backpack",
    )

    assert _role(product) == "product"


def test_kickstarter_is_a_product_record():
    product = _product("Unknown project", "Campaign description", "kickstarter")

    assert _role(product) == "product"
