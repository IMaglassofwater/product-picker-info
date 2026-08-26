"""Tests for commodity and red-ocean rules."""

from candidate_pool import build_consumer_trend_candidate
from commodity_filter import filter_commodity
from models import Product
from scrapers.amazon_trends import filter_amazon_trend


def _product(title: str, raw_data: dict | None = None) -> Product:
    return Product(
        project_id="B0TEST1234", source_platform="amazon",
        url="https://www.amazon.com/dp/B0TEST1234", title=title,
        description=title, category="Home & Kitchen",
        image_url="https://images.example.com/item.jpg",
        raw_data=raw_data or {"source_list": "new_releases"},
    )


def test_generic_bathroom_rug_is_commodity():
    result = filter_commodity(_product("Soft absorbent non-slip machine washable bathroom rug"))
    assert result.commodity_status == "COMMODITY"
    assert "generic_bath_mat" in result.commodity_flags


def test_generic_tumbler_is_not_promising():
    assert filter_commodity(_product("Basic insulated stainless steel tumbler")).commodity_status in {"COMMODITY", "REVIEW"}


def test_generic_lunch_box_is_not_promising():
    assert filter_commodity(_product("Insulated lunch box 3.5L")).commodity_status in {"COMMODITY", "REVIEW"}


def test_large_canopy_has_bulky_shipping_flag():
    result = filter_commodity(_product("10x10 large shelter pop up canopy tent"))
    assert result.commodity_status == "COMMODITY"
    assert "bulky_shipping" in result.commodity_flags


def test_ergonomic_can_opener_can_be_promising():
    result = filter_commodity(_product("Multifunctional can opener with oversized knob and comfortable handle"))
    assert result.commodity_status in {"REVIEW", "PROMISING"}
    assert "ergonomic_improvement" in result.commodity_flags


def test_clearly_modular_foldable_product_is_promising():
    result = filter_commodity(_product("Modular foldable organizer with adjustable storage modules"))
    assert result.commodity_status == "PROMISING"
    assert "modular_design" in result.commodity_flags


def test_high_rank_does_not_override_commodity():
    result = filter_commodity(_product("Basic bathroom rug", {"rank": 1, "source_list": "new_releases"}))
    assert result.commodity_status == "COMMODITY"


def test_many_reviews_do_not_override_commodity():
    result = filter_commodity(_product("Basic lunch box", {"review_count": 50000, "source_list": "new_releases"}))
    assert result.commodity_status == "COMMODITY"


def test_food_contact_container_is_not_treated_as_ingestible():
    result = filter_commodity(_product("Airtight food container and mason jar with lid"))
    assert result.commodity_status in {"COMMODITY", "REVIEW"}
    assert "regulated" not in result.commodity_flags


def test_complex_electronics_cannot_enter_consumer_candidate_pool():
    product = _product("Wireless robot camera organizer")
    trend = filter_amazon_trend(product)
    commodity = filter_commodity(product)
    candidate = build_consumer_trend_candidate(
        product, status=trend.status, feasibility_score=trend.feasibility_score,
        market_signal_score=trend.market_signal_score,
        micro_innovation_score=trend.micro_innovation_score,
        signals=trend.signals, reason=trend.reason,
        commodity_status=commodity.commodity_status,
    )
    assert trend.status == "rejected"
    assert candidate is None
