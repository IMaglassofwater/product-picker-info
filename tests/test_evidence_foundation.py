"""Phase 11B evidence-first shadow mode tests."""

from __future__ import annotations

import sqlite3

import db
from evidence_foundation import (
    ProductIdentity,
    assess_evidence_strength,
    classify_concrete_product,
    classify_eligibility,
    extract_evidence,
    family_match,
    normalize_identity,
    normalize_amazon_title,
    normalize_reddit_title,
)
from evidence_shadow import backfill_historical, process_products_for_run, project_product
from models import Product


def product(source="amazon", title="Compact desk organizer", description="Simple organizer", raw=None, index=1):
    return Product(
        f"p-{index}", source, f"https://example.com/{source}/{index}", title,
        description, "home", f"https://example.com/{index}.jpg", raw or {},
    )


def test_observation_membership_is_run_based_and_first_seen_is_stable(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "shadow.sqlite")
    item = product(raw={"rating": 4.5, "review_count": 80})
    assert db.save_products([item]) == (1, 0)
    first_seen = db.get_product_lifecycle(item.url)["first_seen_at"]
    run_a = db.start_pipeline_run()
    assert process_products_for_run(run_a, [item], existing_urls=set())["observed"] == 1
    db.finish_pipeline_run(run_a, "COMPLETED")
    assert db.save_products([item]) == (0, 1)
    run_b = db.start_pipeline_run()
    assert process_products_for_run(run_b, [item], existing_urls={item.url})["observed"] == 1
    db.finish_pipeline_run(run_b, "COMPLETED")
    assert db.get_product_lifecycle(item.url)["first_seen_at"] == first_seen
    assert len(db.get_products_for_run(run_a)) == len(db.get_products_for_run(run_b)) == 1


def test_eligibility_rejects_known_films():
    for title in (
        "Erotica - MFA Student Film", "O England! - Short Film",
        "AND THE SEA, a feature film", "AT NIGHT, WE PLAY Film Festival Support",
    ):
        result = classify_eligibility(product("indiegogo", title, "Please support this film"))
        assert (result.content_type, result.eligibility_status) == ("NON_PRODUCT_CONTENT", "INELIGIBLE")


def test_source_defaults_accept_software_physical_and_product_design():
    assert classify_eligibility(product("product_hunt", "Ninjo AI", "AI sales app")).content_type == "SOFTWARE_PRODUCT"
    assert classify_eligibility(product("amazon", "Can opener")).content_type == "PHYSICAL_PRODUCT"
    design = classify_eligibility(product("yanko_design", "Foldable travel lamp", "A compact lamp design"))
    assert (design.content_type, design.eligibility_status) == ("PRODUCT_DESIGN", "ELIGIBLE")
    kickstarter = classify_eligibility(product("kickstarter", "Travel backpack", "Compact bag"))
    assert kickstarter.eligibility_status == "ELIGIBLE"


def test_source_title_preserved_and_vague_my_is_normalized():
    item = product("reddit_arctic_shift", "My", "This is my pocket leather journal cover")
    identity = normalize_identity(item, classify_eligibility(item))
    assert identity.source_title == "My"
    assert identity.normalized_product_name == "Pocket Leather Journal Cover"
    assert identity.normalized_product_name_zh == "口袋皮革笔记本套"
    assert identity.confidence == "HIGH"


def test_unresolved_identity_does_not_hallucinate():
    item = product("reddit_arctic_shift", "My", "Here is what I use")
    identity = normalize_identity(item, classify_eligibility(item))
    assert identity.normalized_product_name is None
    assert identity.confidence == "UNRESOLVED"


def test_family_exact_fuzzy_and_overmerge_protection():
    exact_a = family_match(ProductIdentity("Desk organizer", "Desk Organizer", None, "source", "MEDIUM"), "PHYSICAL_PRODUCT")
    exact_b = family_match(ProductIdentity("Desk organizers", "Desk Organizers", None, "source", "MEDIUM"), "PHYSICAL_PRODUCT")
    assert exact_a.family_key == exact_b.family_key
    commuter = family_match(ProductIdentity("20L", "20L Commuter Backpack", None, "source", "MEDIUM"), "PHYSICAL_PRODUCT")
    travel = family_match(ProductIdentity("25L", "25L Work Travel Backpack", None, "source", "MEDIUM"), "PHYSICAL_PRODUCT")
    camera = family_match(ProductIdentity("Camera", "Compact Camera Backpack", None, "source", "MEDIUM"), "PHYSICAL_PRODUCT")
    hydration = family_match(ProductIdentity("Hydration", "Hydration Backpack", None, "source", "MEDIUM"), "PHYSICAL_PRODUCT")
    assert commuter.family_key == travel.family_key
    assert len({commuter.family_key, camera.family_key, hydration.family_key}) == 3


def test_source_native_evidence_and_strength_are_explainable():
    reddit = product("reddit_arctic_shift", raw={"score": 24, "num_comments": 18, "subreddit": "onebag"})
    facts = extract_evidence(reddit)
    result = assess_evidence_strength(reddit.source_platform, facts)
    assert result.strength == "MODERATE"
    assert "comments" in result.metrics_used and any("18 comments" in reason for reason in result.reasons)
    amazon = product("amazon", raw={"rating": 4.6, "review_count": 3200, "rank": 3})
    assert assess_evidence_strength("amazon", extract_evidence(amazon)).strength == "STRONG"


def test_cross_source_evidence_strengthens_but_does_not_become_opportunity_score():
    item = product("reddit_arctic_shift", raw={"score": 1, "num_comments": 1})
    strength = assess_evidence_strength("reddit_arctic_shift", extract_evidence(item), independent_source_count=2)
    assert strength.strength == "MODERATE"
    assert any("2 independent sources" in reason for reason in strength.reasons)


def test_daily_discovery_includes_all_eligible_families_without_ai_or_top_n(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "discovery.sqlite")
    names = [f"Artifact {chr(96 + first)}{chr(96 + second)}" for first in range(1, 6) for second in range(1, 6)]
    items = [product(index=i, title=name) for i, name in enumerate(names, 1)]
    assert db.save_products(items) == (25, 0)
    run_id = db.start_pipeline_run()
    result = process_products_for_run(run_id, items, existing_urls=set())
    assert result["observed"] == 25
    db.finish_pipeline_run(run_id, "COMPLETED")
    discovery = db.get_daily_discovery(run_id)
    assert len(discovery) == 25
    assert all(entry["latest_run_id"] == run_id for entry in discovery)
    with sqlite3.connect(db.DB_PATH) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ai_triage_results").fetchone()[0] == 0


def test_evidence_projection_defers_remaining_products_after_deadline(monkeypatch):
    items = [product(index=41), product(index=42)]
    monkeypatch.setattr(
        db, "get_product_record_by_url",
        lambda _url: (_ for _ in ()).throw(AssertionError("DB must not be touched")),
    )
    result = process_products_for_run(
        "run-deadline", items, deadline_monotonic=10.0, monotonic=lambda: 10.0,
    )
    assert result["processed"] == 0
    assert result["deferred"] == 2


def test_ambiguous_records_are_observed_but_not_in_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "ambiguous.sqlite")
    item = product("reddit_arctic_shift", "Thoughts?", "Interesting idea", index=4)
    db.save_products([item])
    run_id = db.start_pipeline_run()
    process_products_for_run(run_id, [item])
    db.finish_pipeline_run(run_id, "COMPLETED")
    assert len(db.get_observations_for_run(run_id)) == 1
    assert db.get_daily_discovery(run_id) == []


def test_historical_backfill_preserves_products_feedback_and_has_no_fake_observations(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "backfill.sqlite")
    item = product(index=8)
    db.save_products([item])
    record = db.get_product_record_by_url(item.url)
    assert db.save_user_feedback("product", str(record["id"]), "FAVORITE")
    before = db.get_shadow_counts()
    report = backfill_historical()
    after = db.get_shadow_counts()
    assert report["processed"] == 1
    assert before["products"] == after["products"] == 1
    assert before["user_product_feedback"] == after["user_product_feedback"] == 1
    assert after["product_observations"] == 0
    with sqlite3.connect(db.DB_PATH) as connection:
        family_id = connection.execute("SELECT family_id FROM product_family_members").fetchone()[0]
    assert db.get_family_feedback(family_id)[0]["feedback_type"] == "FAVORITE"


def test_sqlite_and_postgres_schemas_contain_additive_shadow_tables():
    from postgres_backend import POSTGRES_SCHEMA
    for table in (
        "product_observations", "product_eligibility", "product_identities",
        "product_families", "product_family_members", "source_evidence_snapshots",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in POSTGRES_SCHEMA
    assert "concrete_product_status" in POSTGRES_SCHEMA


def test_trip_itinerary_and_broad_redesign_are_non_concrete():
    cases = (
        product("reddit_arctic_shift", "Trip Report: 3 Weeks in Europe", "My packing experience"),
        product("reddit_arctic_shift", "2 weeks in Japan during winter", "Travel itinerary"),
        product("reddit_arctic_shift", "If you could redesign one piece of travel gear", "Broad ideas"),
    )
    for item in cases:
        result = classify_concrete_product(item, classify_eligibility(item))
        assert result.status == "NON_CONCRETE"


def test_multi_item_edc_is_non_concrete_but_one_product_demand_is_concrete():
    loadout = product("reddit_arctic_shift", "My EDC loadout", "Knife, wallet, lamp and pouch")
    assert classify_concrete_product(loadout, classify_eligibility(loadout)).status == "NON_CONCRETE"
    backpack = product(
        "reddit_arctic_shift", "Looking for a 20-25L commuter backpack",
        "One compact backpack for work",
    )
    concrete = classify_concrete_product(backpack, classify_eligibility(backpack))
    identity = normalize_identity(backpack, classify_eligibility(backpack), concrete=concrete)
    assert concrete.status == "CONCRETE"
    assert identity.normalized_product_name == "20–25L Commuter Backpack"


def test_catalog_and_specific_design_concrete_rules():
    amazon = product("amazon", "GORILLA GRIP Heavy Duty Manual Can Opener")
    software = product("product_hunt", "Ninjo AI", "AI sales agents on any channel")
    design = product("yanko_design", "This Desk Lamp Solves the Cord Problem", "A specific desk lamp")
    for item in (amazon, software, design):
        assert classify_concrete_product(item, classify_eligibility(item)).status == "CONCRETE"


def test_listicle_is_not_concrete_even_when_it_mentions_products():
    item = product(
        "yanko_design", "7 Best Camping Gadgets and Gear", "A lamp, bag, tool and bottle collection",
    )
    result = classify_concrete_product(item, classify_eligibility(item))
    assert result.status == "NON_CONCRETE"


def test_source_aware_title_shortening():
    assert normalize_amazon_title(
        "GORILLA GRIP Heavy Duty Stainless Steel Smooth Edge Manual Can Opener, Black | Kitchen Tool"
    ) == "GORILLA GRIP Manual Can Opener"
    assert normalize_reddit_title("Looking for key organiser") == "Key Organizer"
    item = product("product_hunt", "Ninjō AI", "AI sales agents on any channel")
    eligibility = classify_eligibility(item)
    concrete = classify_concrete_product(item, eligibility)
    assert normalize_identity(item, eligibility, concrete=concrete).normalized_product_name == "Ninjō AI — AI Sales Agent"


def test_daily_discovery_requires_concrete_and_excludes_trip_family(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "concrete.sqlite")
    valid = product("amazon", "GORILLA GRIP Manual Can Opener", index=30)
    trip = product("reddit_arctic_shift", "Trip Report: 3 Weeks in Europe", "Travel bag packing", index=31)
    db.save_products([valid, trip])
    run_id = db.start_pipeline_run()
    process_products_for_run(run_id, [valid, trip])
    db.finish_pipeline_run(run_id, "COMPLETED")
    discovery = db.get_daily_discovery(run_id)
    assert [item["canonical_name"] for item in discovery] == ["GORILLA GRIP Manual Can Opener"]


def test_family_canonical_name_uses_short_high_confidence_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "canonical.sqlite")
    first = product("amazon", "GORILLA GRIP Heavy Duty Stainless Steel Manual Can Opener, Black", index=40)
    second = product("amazon", "GORILLA GRIP Manual Can Opener, Red", index=41)
    db.save_products([first, second])
    backfill_historical()
    with sqlite3.connect(db.DB_PATH) as connection:
        names = [row[0] for row in connection.execute("SELECT canonical_name FROM product_families")]
    assert names == ["GORILLA GRIP Manual Can Opener"]


def test_generic_advice_and_multi_product_comparison_are_not_concrete():
    cases = (
        product("reddit_arctic_shift", "Remaining Gear Advice", "What should I replace?"),
        product("reddit_arctic_shift", "Packing and bag advice", "Help optimize my setup"),
        product(
            "reddit_arctic_shift",
            "I tested five backpacking pillows",
            "A comparison of several different pillows",
        ),
        product("reddit_arctic_shift", "Night walk bag dump", "My backpack, pouch and wallet"),
        product("reddit_arctic_shift", "Today's EDC", "My everyday items"),
        product("reddit_arctic_shift", "What backpack would you recommend for me?", "Any bag"),
    )
    for item in cases:
        result = classify_concrete_product(item, classify_eligibility(item))
        assert result.status == "NON_CONCRETE"


def test_reddit_name_uses_title_without_description_contamination():
    item = product(
        "reddit_arctic_shift",
        "Dragonfly Ultra 36L",
        "I also carry a small fanny pack for day trips",
    )
    eligibility = classify_eligibility(item)
    concrete = classify_concrete_product(item, eligibility)
    identity = normalize_identity(item, eligibility, concrete=concrete)
    assert identity.normalized_product_name == "Dragonfly Ultra 36L Backpack"


def test_backpack_size_ranges_and_use_cases_do_not_overmerge():
    commuter = family_match(
        ProductIdentity("20L", "20–25L Commuter Backpack", None, "source", "HIGH"),
        "PHYSICAL_PRODUCT",
    )
    travel = family_match(
        ProductIdentity("45L", "40–45L Travel Backpack", None, "source", "HIGH"),
        "PHYSICAL_PRODUCT",
    )
    work = family_match(
        ProductIdentity("Work", "Non-Tactical Work Backpack", None, "source", "HIGH"),
        "PHYSICAL_PRODUCT",
    )
    assert len({commuter.family_key, travel.family_key, work.family_key}) == 3
