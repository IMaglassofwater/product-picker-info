"""Tests for free creative content routing and hard feasibility rules."""

import sqlite3

import db
from candidate_pool import build_inspiration_candidate
from creative_content_filter import filter_creative_content
from models import Product


def _product(
    title: str,
    description: str,
    *,
    categories: list[str],
    url: str = "https://www.yankodesign.com/example/",
) -> Product:
    return Product(
        project_id=url.rstrip("/").rsplit("/", 1)[-1],
        source_platform="yanko_design",
        url=url,
        title=title,
        description=description,
        category=categories[0],
        image_url="https://www.yankodesign.com/images/example.jpg",
        raw_data={
            "categories": categories,
            "tags": categories,
            "published_at": "Tue, 25 Aug 2026 08:00:00 +0000",
            "image_url": "https://www.yankodesign.com/images/example.jpg",
        },
    )


def test_architecture_does_not_enter_candidate_pool():
    product = _product(
        "Compact forest cabin",
        "Architecture for a small residential building in a remote forest.",
        categories=["Architecture"],
    )
    result = filter_creative_content(product)

    assert result.content_type == "architecture"
    assert build_inspiration_candidate(product, result) is None


def test_vehicle_does_not_enter_candidate_pool():
    product = _product(
        "Compact camper trailer",
        "An automotive vehicle with a folding kitchen and sleeping space.",
        categories=["Automotive", "Outdoor"],
    )
    result = filter_creative_content(product)

    assert result.content_type == "vehicle"
    assert build_inspiration_candidate(product, result) is None


def test_complex_technology_does_not_enter_candidate_pool():
    product = _product(
        "AI home robot",
        "A battery powered artificial intelligence robot with wireless control.",
        categories=["Technology", "Robotics"],
    )
    result = filter_creative_content(product)

    assert result.content_type == "technology_complex"
    assert build_inspiration_candidate(product, result) is None


def test_simple_physical_product_enters_inspiration_pool():
    product = _product(
        "Compact modular travel pouch",
        "A simple non-electronic fabric pouch with modular storage pockets for daily travel.",
        categories=["Product Design", "Accessories"],
    )
    result = filter_creative_content(product)
    candidate = build_inspiration_candidate(product, result)

    assert result.content_type == "physical_product"
    assert result.eligible is True
    assert candidate is not None
    assert candidate.candidate_type == "inspiration_product"
    assert candidate.market_validation_score == 0


def test_simple_concept_product_can_enter_inspiration_pool():
    product = _product(
        "Concept modular key organizer",
        "A simple non-electronic pocket organizer concept with a manual clip for everyday carry.",
        categories=["Product Design", "Accessories"],
    )
    result = filter_creative_content(product)
    candidate = build_inspiration_candidate(product, result)

    assert result.content_type == "concept_product"
    assert result.eligible is True
    assert candidate is not None
    assert candidate.demand_score == 0
    assert candidate.market_validation_score == 0


def test_duplicate_inspiration_url_is_not_saved_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "candidate.db")
    product = _product(
        "Compact modular travel pouch",
        "A simple non-electronic fabric pouch with modular storage pockets for daily travel.",
        categories=["Product Design", "Accessories"],
    )
    candidate = build_inspiration_candidate(
        product, filter_creative_content(product)
    )
    assert candidate is not None

    saved, duplicates = db.save_candidates([candidate, candidate])

    assert (saved, duplicates) == (1, 1)
    with sqlite3.connect(db.DB_PATH) as connection:
        assert connection.execute(
            "SELECT candidate_type FROM micro_innovation_candidates"
        ).fetchone()[0] == "inspiration_product"
