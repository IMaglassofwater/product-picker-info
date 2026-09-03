"""Phase 11H deterministic Daily Picks and grounded User Voice tests."""

from __future__ import annotations

import db
from daily_picks import (
    SOURCE_CAPS, available_source_options, build_daily_picks,
    prepare_discovery_item, render_wxpusher_pick_chunks,
    select_daily_picks, source_display_label, today_pick_items,
)
from user_voice import classify_reddit_voice, extract_user_voice, normalize_user_voice_items, summarize_user_voice


def test_reddit_voice_semantics_distinguish_experience_need_and_discussion():
    assert classify_reddit_voice("I owned this tent for five years and used it every summer.") == "AUTHOR_EXPERIENCE"
    assert classify_reddit_voice("Can anyone recommend a tent for strong winds?") == "USER_NEED"
    assert classify_reddit_voice("Which of these two tents is better?") == "PRODUCT_DISCUSSION"


def item(index: int, source: str, *, evidence="MODERATE", kind="PHYSICAL_PRODUCT", raw=None, description="A concrete keyboard product.") -> dict:
    return {
        "family_id": index, "display_order": index, "canonical_name": f"Product {index}",
        "canonical_name_zh": f"产品{index}", "factual_description": description,
        "factual_description_zh": description, "product_type": kind,
        "evidence_strength": evidence, "evidence_reasons": [f"{source} factual evidence"],
        "source_platforms": [source], "source_records": [{
            "product_id": index, "project_id": str(index), "source_platform": source,
            "url": f"https://example.test/{source}/{index}", "description": description,
            "raw_data": raw or {},
        }],
    }


def synthetic_dataset() -> dict:
    sources = ["amazon"] * 8 + ["kickstarter"] * 7 + ["indiegogo"] * 5 + ["reddit_arctic_shift"] * 5 + ["product_hunt"] * 6 + ["yanko_design"] * 3
    values = [item(i, source, evidence="STRONG" if i % 3 == 0 else "MODERATE", kind="PRODUCT_DESIGN" if source == "yanko_design" else "SOFTWARE_PRODUCT" if source == "product_hunt" else "PHYSICAL_PRODUCT", raw={"review_count": 1000 - i, "backers": 500 - i, "score": 100 - i, "num_comments": 20}) for i, source in enumerate(sources, 1)]
    return {"run_id": "daily:test", "items": values, "item_count": len(values)}


def test_caps_diversity_determinism_no_duplicate_and_no_ai_gate():
    data = synthetic_dataset()
    first = select_daily_picks(data); second = select_daily_picks(data)
    assert [x["family_id"] for x in first] == [x["family_id"] for x in second]
    assert len({x["family_id"] for x in first}) == len(first)
    counts = {source: sum(x["primary_source"] == source for x in first) for source in SOURCE_CAPS}
    assert all(counts[source] <= cap for source, cap in SOURCE_CAPS.items())
    assert len({x["primary_source"] for x in first}) >= 4
    assert len({x["product_type"] for x in first}) >= 2
    assert not any("score" in " ".join(x["selection_reasons"]).casefold() for x in first)


def test_weak_source_is_not_forced_and_exploration_is_factual():
    data = synthetic_dataset()
    data["items"].append(item(99, "other", evidence="WEAK", kind="PRODUCT_DESIGN"))
    picks = select_daily_picks(data)
    assert sum(x["primary_source"] == "other" for x in picks) <= 1
    assert any("探索发现" in x["selection_reasons"] for x in picks)


def test_obvious_non_product_never_enters_picks_and_target_is_not_forced():
    data = {"run_id": "daily:test", "items": [
        item(1, "indiegogo", evidence="STRONG", description="A short film about a fan."),
        item(2, "amazon", evidence="MODERATE"),
        item(3, "product_hunt", evidence="WEAK", kind="SOFTWARE_PRODUCT"),
    ]}
    picks = select_daily_picks(data, target=20)
    assert [value["family_id"] for value in picks] == [2, 3]
    assert len(picks) < 20


def test_crowdfunding_narrative_without_product_object_is_not_a_pick():
    narrative = item(8, "indiegogo", evidence="MODERATE", description="A young fan meets an actor and learns about relationships.")
    narrative["canonical_name"] = "Fanatic"
    assert select_daily_picks({"run_id": "daily:test", "items": [narrative]}) == []
    narrative["product_type"] = "SOFTWARE_PRODUCT"
    assert select_daily_picks({"run_id": "daily:test", "items": [narrative]}) == []


def test_persistence_parity_and_full_discovery_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "picks.sqlite")
    assert db.init_db()
    # Minimal FK parents for the persisted projection.
    with db._connect() as connection:
        connection.execute("INSERT INTO pipeline_runs(run_id,started_at,status,stats_json) VALUES ('p','2026-01-01','COMPLETED','{}')")
        connection.execute("INSERT INTO daily_discovery_runs(run_id,pipeline_run_id,discovery_date,generated_at,status,item_count,metadata_json) VALUES ('daily:test','p','2026-01-01','2026-01-01','COMPLETED',20,'{}')")
        for value in synthetic_dataset()["items"]:
            connection.execute("INSERT INTO product_families(id,family_key,canonical_name,product_type,status,grouping_version,first_seen_at,last_seen_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)", (value["family_id"], f"f-{value['family_id']}", value["canonical_name"], value["product_type"], "ACTIVE", "v", "2026-01-01", "2026-01-01", "2026-01-01", "2026-01-01"))
    full = synthetic_dataset(); before = [x["family_id"] for x in full["items"]]
    result = build_daily_picks(full)
    loaded = db.get_persisted_daily_picks(daily_discovery_run_id="daily:test")
    today = today_pick_items(loaded)
    wx = [family_id for chunk in render_wxpusher_pick_chunks(loaded) for family_id in chunk["family_ids"]]
    assert [x["family_id"] for x in loaded["items"]] == [x["family_id"] for x in today] == wx
    assert [x["family_id"] for x in full["items"]] == before
    assert 15 <= result["item_count"] <= 25


def test_user_voice_requires_text_traceability_and_never_infers_sentiment():
    aggregate = item(1, "amazon", raw={"rating": 4.9, "review_count": 9000})
    assert extract_user_voice(aggregate) == []
    reddit = item(2, "reddit_arctic_shift", raw={"score": 50, "num_comments": 10, "author": "public-user"}, description="I use this organizer every day.")
    voice = extract_user_voice(reddit)
    assert len(voice) == 1 and voice[0]["source_url"]
    summary = summarize_user_voice(voice)
    assert summary["author_experience"][0]["text"] == "I use this organizer every day."
    assert summary["commenter_feedback"] == []


def test_unix_published_time_is_normalized_for_postgres():
    reddit = item(7, "reddit_arctic_shift", raw={"created_utc": 1_700_000_000}, description="A public user post.")
    assert extract_user_voice(reddit)[0]["published_at"].endswith("+00:00")


def test_explicit_comment_text_is_preserved_not_fabricated():
    value = item(3, "product_hunt", raw={"comment_texts": [{"text": "The export is useful", "url": "https://example.test/comment/3"}]})
    voice = extract_user_voice(value)
    assert [x["original_text"] for x in voice] == ["The export is useful"]
    assert voice[0]["source_url"].endswith("/comment/3")
    assert voice[0]["voice_type"] == "COMMENTER_FEEDBACK"


def test_reddit_author_text_is_not_commenter_feedback_and_is_deduplicated():
    reddit = item(9, "reddit_arctic_shift", raw={"score": 5, "num_comments": 12}, description="I bought and use this pouch every day.")
    reddit["source_records"].append(dict(reddit["source_records"][0]))
    voice = extract_user_voice(reddit)
    assert len(voice) == 1
    assert voice[0]["voice_type"] == "AUTHOR_EXPERIENCE"
    summary = summarize_user_voice(voice)
    assert len(summary["author_experience"]) == 1
    assert summary["commenter_feedback"] == []


def test_reddit_permalink_is_preferred_over_direct_media_url():
    reddit = item(10, "reddit_arctic_shift", raw={
        "permalink": "/r/BuyItForLife/comments/abc/product/", "num_comments": 8,
    }, description="I owned this case for three years.")
    reddit["source_records"][0]["url"] = "https://i.redd.it/image.jpeg"
    assert extract_user_voice(reddit)[0]["source_url"] == "https://www.reddit.com/r/BuyItForLife/comments/abc/product/"


def test_legacy_reddit_voice_is_classified_without_database_mutation():
    values = normalize_user_voice_items([{
        "source": "reddit_arctic_shift", "original_text": "I used this tent and the pole broke.",
        "source_url": "https://reddit.com/r/camping/comments/a/x", "voice_type": "OTHER_DISCUSSION",
    }])
    assert values[0]["voice_type"] == "AUTHOR_EXPERIENCE"


def test_invalid_reddit_identity_is_excluded_but_remains_in_full_dataset():
    reddit = item(11, "reddit_arctic_shift", evidence="STRONG", description="General discussion without a concrete product.")
    reddit["canonical_name"] = "What do you all think?"
    reddit["source_records"][0]["source_title"] = reddit["canonical_name"]
    dataset = {"run_id": "daily:test", "items": [reddit], "item_count": 1}
    assert prepare_discovery_item(reddit)["identity_confidence"] == "LOW"
    assert select_daily_picks(dataset) == []
    assert dataset["items"][0]["canonical_name"] == "What do you all think?"


def test_near_duplicate_tumblers_do_not_both_use_daily_pick_slots():
    first = item(20, "amazon", evidence="STRONG"); first["canonical_name"] = "Simple Insulated Tumbler"
    second = item(21, "amazon", evidence="STRONG"); second["canonical_name"] = "STANLEY Insulated Tumbler"
    picks = select_daily_picks({"run_id": "daily:test", "items": [first, second]})
    assert len(picks) == 1


def test_weak_concrete_product_hunt_software_has_fair_access_without_quota():
    software = [item(index, "product_hunt", evidence="WEAK", kind="SOFTWARE_PRODUCT", description="A concrete software tool.") for index in range(30, 35)]
    for value in software:
        value["canonical_name"] = f"Tool {value['family_id']} — Developer Tool"
    picks = select_daily_picks({"run_id": "daily:test", "items": software})
    assert 1 <= len(picks) <= SOURCE_CAPS["product_hunt"]
    assert all(value["basket"] == "软件 / 数字产品" for value in picks)
    assert all(value["evidence_strength"] == "WEAK" for value in picks)
    assert len(picks) < len(software)  # fair access, not a forced platform quota


def test_specific_software_identity_ranks_ahead_of_vague_tagline():
    vague = item(60, "product_hunt", evidence="WEAK", kind="SOFTWARE_PRODUCT", description="You're coming out tonight")
    vague["canonical_name"] = "CrowdVolt — You're coming out tonight"
    concrete = item(61, "product_hunt", evidence="WEAK", kind="SOFTWARE_PRODUCT", description="A developer tool for indexing APIs.")
    concrete["canonical_name"] = "Developer Index — Developer Tool"
    picks = select_daily_picks({"run_id": "daily:test", "items": [vague, concrete]}, target=1)
    assert picks[0]["family_id"] == 61


def test_source_labels_keep_canonical_ids_and_hide_zero_count_sources():
    values = [item(40, "reddit_arctic_shift"), item(41, "reddit_software"), item(42, "product_hunt")]
    assert source_display_label("reddit_arctic_shift") == "Reddit"
    assert source_display_label("reddit_software") == "Software Reddit"
    assert available_source_options(values) == [
        ("product_hunt", "Product Hunt"),
        ("reddit_arctic_shift", "Reddit"),
        ("reddit_software", "Software Reddit"),
    ]
    assert "hacker_news" not in dict(available_source_options(values))


def test_build_daily_picks_reads_existing_user_voice_repository(monkeypatch):
    reddit = item(50, "reddit_arctic_shift", evidence="STRONG", description="I bought and used this key organizer.")
    reddit["canonical_name"] = "Looking for key organizer"
    reddit["source_records"][0]["source_title"] = "Looking for key organizer"
    stored = [{
        "source": "reddit_arctic_shift", "original_text": "I bought and used this key organizer.",
        "source_url": "https://www.reddit.com/r/edc/comments/50/key/", "voice_type": "OTHER_DISCUSSION",
    }]
    monkeypatch.setattr(db, "get_user_voice_items", lambda family_id: stored)
    monkeypatch.setattr(db, "persist_daily_picks_snapshot", lambda *args: "picks:test")
    monkeypatch.setattr(db, "save_user_voice_items", lambda values: (0, len(values)))
    result = build_daily_picks({"run_id": "daily:test", "items": [reddit]}, persist=True)
    summary = result["items"][0]["user_voice_summary"]
    assert summary["author_experience"][0]["text"].startswith("I bought")
    assert summary["commenter_feedback"] == []
