"""Tests for the deterministic opportunity rule filter."""

import pytest

from models import Product
from rule_filter import FilterResult, filter_product


def _product(
    title: str,
    description: str = "Product description",
    raw_data: dict | None = None,
) -> Product:
    return Product(
        project_id="rule-1",
        source_platform="reddit",
        url="https://example.com/rule-product",
        title=title,
        description=description,
        category="General",
        image_url="https://example.com/rule-product.jpg",
        raw_data=raw_data or {},
    )


def test_edc_product_receives_higher_score():
    neutral_result = filter_product(_product("Simple product"))
    edc_result = filter_product(_product("EDC organizer tool"))

    assert edc_result.filter_score > neutral_result.filter_score
    assert edc_result.status == "candidate"


def test_medical_product_score_is_reduced():
    neutral_result = filter_product(_product("Simple product"))
    medical_result = filter_product(_product("Medical medicine organizer"))

    assert medical_result.filter_score < neutral_result.filter_score
    assert medical_result.status == "rejected"


def test_filter_result_structure():
    result = filter_product(_product("Travel accessory"))

    assert isinstance(result, FilterResult)
    assert isinstance(result.filter_score, int)
    assert result.status in {"candidate", "rejected", "uncertain"}
    assert isinstance(result.reason, str)
    assert result.opportunity_type in {
        "physical",
        "software",
        "inspiration",
        "uncertain",
    }


@pytest.mark.parametrize(
    ("title", "description"),
    [
        ("Superflow AI", "AI agents that QA your website before launch"),
        ("Tiny Funnel", "Funnel analytics you'll actually understand"),
        ("Balsa UI", "Create design systems, build with agents"),
    ],
)
def test_real_software_examples(title, description):
    result = filter_product(_product(title, description))

    assert result.opportunity_type == "software"


@pytest.mark.parametrize(
    ("title", "description"),
    [
        ("Portable EDC Organizer", "Compact pouch for carrying everyday tools"),
        ("Travel Cable Holder", "Small physical organizer for charging cables"),
        ("Camping Gear Clip", "Lightweight clip for attaching gear to a backpack"),
    ],
)
def test_real_physical_examples(title, description):
    result = filter_product(_product(title, description))

    assert result.opportunity_type == "physical"


def test_uncertain_example_is_not_a_candidate():
    result = filter_product(_product("Mochi", "A tiny companion"))

    assert result.opportunity_type == "uncertain"
    assert result.status == "uncertain"


@pytest.mark.parametrize(
    ("title", "description", "raw_data"),
    [
        (
            "Mochi",
            "A tiny animated cat for every browser tab",
            {"topics": ["Browser Extensions"]},
        ),
        (
            "Vois 2.0",
            "ElevenLabs alternative",
            {"metadata": {"platforms": ["AI software"]}},
        ),
        (
            "Basedash",
            "Live dashboards for anyone you send the link to",
            {"topics": ["Analytics"]},
        ),
        (
            "Origin by Cursor",
            "Git forge built for coding agents",
            {"metadata": {"category": "Developer tools", "platform": "Git"}},
        ),
    ],
)
def test_enriched_product_hunt_software_examples(title, description, raw_data):
    result = filter_product(_product(title, description, raw_data))

    assert result.opportunity_type == "software"


def test_paper_critters_remains_uncertain_without_reliable_type_signals():
    result = filter_product(
        _product("Paper Critters", "Kid friendly paper toys")
    )

    assert result.opportunity_type == "uncertain"
    assert result.status == "uncertain"


def test_kickstarter_funded_reason_is_added_without_reclassification():
    product = _product("Unknown campaign", raw_data={"percent_funded": 150})
    product.source_platform = "kickstarter"

    result = filter_product(product)

    assert result.opportunity_type == "uncertain"
    assert "market validated: funded >= 100%" in result.reason


def test_kickstarter_high_funding_does_not_add_old_strong_label():
    product = _product("Unknown campaign", raw_data={"percent_funded": 350})
    product.source_platform = "kickstarter"

    result = filter_product(product)

    assert "market validated: funded >= 100%" in result.reason
    assert "strong crowdfunding validation" not in result.reason
