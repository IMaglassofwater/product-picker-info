"""Phase 11H.1C narrow Product Direction and rendered-card tests."""

from pathlib import Path

from daily_picks import build_daily_picks, select_daily_picks
from product_directions import build_product_directions
from scripts.phase11h_preview import write_previews


def family(index: int, name: str, source="amazon", *, kind="PHYSICAL_PRODUCT", evidence="MODERATE", raw=None, description=None):
    return {
        "family_id": index, "display_order": index, "canonical_name": name,
        "canonical_name_zh": None, "factual_description": description or f"Factual description for {name}",
        "factual_description_zh": None, "product_type": kind,
        "evidence_strength": evidence, "evidence_reasons": ["factual source evidence"],
        "source_platforms": [source], "identity_valid": True, "identity_confidence": "HIGH",
        "source_records": [{"product_id": index, "project_id": str(index), "source_platform": source,
            "source_title": name, "url": f"https://example.test/{source}/{index}",
            "description": description or f"Factual description for {name}", "raw_data": raw or {}}],
    }


def test_simple_and_stanley_aggregate_and_preserve_members_and_evidence():
    values = [
        family(1, "Simple Insulated Tumbler", raw={"rating": 4.5, "review_count": 3000}),
        family(2, "STANLEY Insulated Tumbler", raw={"rating": 4.7, "review_count": 18000}),
    ]
    directions = build_product_directions(values)
    assert len(directions) == 1
    direction = directions[0]
    assert direction["name_en"] == "Insulated Tumbler"
    assert direction["name_zh"] == "保温杯"
    assert direction["member_family_ids"] == [1, 2]
    assert len(direction["source_evidence"]) == 2
    assert all(value["link_available"] for value in direction["source_evidence"])


def test_narrow_grouping_does_not_merge_tent_sleeping_bag_or_backpack():
    directions = build_product_directions([
        family(1, "Kelty Tent"), family(2, "Compact Sleeping Bag"), family(3, "Travel Backpack"),
        family(4, "Camping Tent Cot"),
    ])
    assert {value["name_en"] for value in directions} == {"Camping Tent", "Camping Tent Cot", "Sleeping Bag", "Travel Backpack"}


def test_unique_product_remains_singleton_direction():
    direction = build_product_directions([family(1, "Olight Ostation 2 Battery Hub")])[0]
    assert direction["aggregation_method"] == "singleton"
    assert direction["member_family_ids"] == [1]


def test_multi_platform_direction_groups_evidence_by_member_and_preserves_links():
    amazon = family(1, "Simple Insulated Tumbler", raw={"rating": 4.5, "review_count": 3000})
    reddit = family(2, "Insulated Tumbler", "reddit_arctic_shift", raw={"score": 86, "num_comments": 42, "subreddit": "BuyItForLife"}, description="I use this insulated tumbler every day.")
    direction = build_product_directions([amazon, reddit])[0]
    assert direction["source_platforms"] == ["amazon", "reddit_arctic_shift"]
    assert {value["source"] for value in direction["source_evidence"]} == {"amazon", "reddit_arctic_shift"}
    assert all(value["url"] for value in direction["source_evidence"])


def test_twenty_direction_target_and_explicit_shortage_reason():
    sources = ["amazon", "kickstarter", "indiegogo", "reddit_arctic_shift", "reddit_software", "product_hunt", "hacker_news", "yanko_design"]
    values = []
    for index in range(1, 33):
        source = sources[index % len(sources)]
        kind = "SOFTWARE_PRODUCT" if source in {"reddit_software", "product_hunt", "hacker_news"} else "PRODUCT_DESIGN" if source == "yanko_design" else "PHYSICAL_PRODUCT"
        noun = "Developer Tool" if kind == "SOFTWARE_PRODUCT" else "Desk Lamp" if kind == "PRODUCT_DESIGN" else "Desk Organizer"
        value = family(index, f"Distinct {noun} {index}", source, kind=kind, evidence="WEAK" if kind != "PHYSICAL_PRODUCT" else "MODERATE", description=f"A concrete {noun.lower()} with identifier {index}.")
        # Keep each synthetic record a singleton rather than invoking a known
        # narrow aggregation rule.
        values.append(value)
    result = build_daily_picks({"run_id": "daily:test", "items": values}, persist=False, target=20)
    assert result["item_count"] == 20
    assert result["shortage_reason"] == ""
    short = build_daily_picks({"run_id": "daily:short", "items": values[:3]}, persist=False, target=20)
    assert short["item_count"] < 20
    assert "Only" in short["shortage_reason"]


def test_recent_physical_discovery_is_not_labeled_innovation():
    pick = select_daily_picks({"run_id": "daily:test", "items": [family(1, "Ordinary Garden Item")]})[0]
    assert pick["basket"] == "其他产品发现"


def test_html_has_four_part_structure_visible_voice_and_no_opaque_primary_fields(tmp_path: Path):
    polywood = family(1, "POLYWOOD Outdoor Rocking Chair", "reddit_arctic_shift", evidence="STRONG", raw={"score": 80, "num_comments": 20}, description="I bought POLYWOOD outdoor rocking chairs and one rocker failed before replacement.")
    polywood["canonical_name_zh"] = "POLYWOOD 户外摇椅"
    discovery = {"run_id": "daily:test", "item_count": 1, "items": [polywood]}
    picks = build_daily_picks(discovery, persist=False)
    write_previews(tmp_path, discovery, picks)
    html = (tmp_path / "today_picks_preview.html").read_text(encoding="utf-8")
    assert all(value in html for value in ("这是什么", "市场佐证", "用户反馈 / 评论区反馈"))
    assert "I bought POLYWOOD outdoor rocking chairs" in html
    assert "我买过 POLYWOOD 户外摇椅" in html
    assert "查看来源" in html
    assert "为什么今天展示" not in html
    assert "PHYSICAL_PRODUCT" not in html
    assert "该产品为" not in html


def test_empty_feedback_is_one_compact_state_and_counts_do_not_infer_sentiment(tmp_path: Path):
    value = family(1, "Manual Can Opener", raw={"rating": 4.8, "review_count": 9000})
    discovery = {"run_id": "daily:test", "item_count": 1, "items": [value]}
    picks = build_daily_picks(discovery, persist=False)
    write_previews(tmp_path, discovery, picks)
    html = (tmp_path / "today_picks_preview.html").read_text(encoding="utf-8")
    assert html.count("暂无可用的真实文字反馈") == 1
    assert "原帖作者体验：暂无" not in html and "评论区反馈：暂无" not in html


def test_known_reddit_author_experience_is_visible_in_rendered_html(tmp_path: Path):
    values = [
        family(1, "POLYWOOD Outdoor Rocking Chair", "reddit_arctic_shift", evidence="STRONG", raw={"score": 80, "num_comments": 20}, description="I bought POLYWOOD outdoor rocking chairs and one rocker failed before replacement."),
        family(2, "WinkBed Luxury Firm Mattress", "reddit_arctic_shift", evidence="STRONG", raw={"score": 90, "num_comments": 30}, description="I used a WinkBed Luxury Firm mattress and it failed in under 4 years; the warranty claim was denied."),
        family(3, "OtterBox Phone Case", "reddit_arctic_shift", evidence="STRONG", raw={"score": 70, "num_comments": 10}, description="I used an OtterBox Defender phone case until it broke and received a warranty replacement."),
    ]
    discovery = {"run_id": "daily:test", "item_count": 3, "items": values}
    write_previews(tmp_path, discovery, build_daily_picks(discovery, persist=False))
    html = (tmp_path / "today_picks_preview.html").read_text(encoding="utf-8")
    assert "I bought POLYWOOD outdoor rocking chairs" in html
    assert "WinkBed Luxury Firm mattress" in html
    assert "OtterBox Defender phone case" in html
    assert html.count("用户反馈 / 评论区反馈") == 3


def test_feedback_render_uses_chinese_primary_english_secondary_and_compact_metadata(tmp_path: Path):
    value = family(1, "POLYWOOD Outdoor Rocking Chair", "reddit_arctic_shift", evidence="STRONG",
                   raw={"score": 80, "num_comments": 20},
                   description="Friends, I totally have to gush about the customer service at Polywood -- the outdoor furniture manufacturer. In 2020, my wife bought me an outdoor rocking chair for our porch. They're made by Polywood. This chair was absolute junk!")
    discovery = {"run_id": "daily:test", "item_count": 1, "items": [value]}
    write_previews(tmp_path, discovery, build_daily_picks(discovery, persist=False))
    html = (tmp_path / "today_picks_preview.html").read_text(encoding="utf-8")
    assert 'class="voice-zh"' in html and 'class="voice-en"' in html
    assert "中文翻译：" not in html and "English Original：" not in html and "作者：" not in html
    assert "代表产品" in html and "查看原文" in html
