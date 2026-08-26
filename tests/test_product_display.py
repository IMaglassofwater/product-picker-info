from dataclasses import dataclass, field

from product_display import (
    ai_display_status,
    build_product_display,
    chinese_ai_content,
    extract_source_metadata,
    product_summary,
)


@dataclass
class DisplayFixture:
    title: str = "Compact key organizer"
    description: str = "A compact organizer designed to hold flat and round keys."
    source_platform: str = "reddit_arctic_shift"
    raw_data: dict = field(default_factory=dict)
    display_title_zh: str = ""
    candidate_id: str = ""
    gemini_reason: str = ""


def labels(metadata):
    return {name: value for name, value in metadata.english}


def test_description_produces_summary_without_ai():
    display = build_product_display(DisplayFixture())
    assert display.product_summary.startswith("A compact organizer")
    assert display.ai_display_status == "NOT_ANALYZED"


def test_summary_falls_back_to_source_metadata_then_title():
    assert product_summary("", {"tagline": "A small desk storage tray."}, "Title") == "A small desk storage tray."
    assert product_summary("", {}, "Product title") == "Product title"
    assert product_summary("", {}, "") == "Description not available."


def test_summary_cleans_html_and_truncates_without_rewriting():
    summary = product_summary("<p>Simple&nbsp;travel pouch</p>", {}, "")
    assert summary == "Simple travel pouch"


def test_ai_pending_is_distinct_from_not_analyzed():
    assert ai_display_status("", False) == "NOT_ANALYZED"
    assert ai_display_status("candidate-1", False) == "AI_PENDING"
    assert ai_display_status("candidate-1", True) == "ANALYZED"


def test_reddit_metadata_allow_list():
    data = labels(extract_source_metadata("reddit_arctic_shift", {"subreddit":"EDC", "score":4, "num_comments":2, "private":"no"}))
    assert data == {"Subreddit":"EDC", "Score":"4", "Comments":"2"}


def test_amazon_metadata_allow_list():
    data = labels(extract_source_metadata("amazon", {"price":"$10", "rating":4.5, "review_count":20, "rank":3}))
    assert {"Price", "Rating", "Reviews", "Rank"} <= set(data)


def test_kickstarter_metadata_allow_list():
    data = labels(extract_source_metadata("kickstarter", {"pledged":15000, "goal":10000, "percent_funded":150, "backers_count":300, "state":"live"}))
    assert data["Funded"] == "150%" and data["Backers"] == "300"


def test_indiegogo_metadata_allow_list():
    data = labels(extract_source_metadata("indiegogo", {"funds_gathered":5000, "funding_percentage":125, "backer_count":50, "campaign_status":"open"}))
    assert data["Funded"] == "125%" and data["Status"] == "open"


def test_product_hunt_metadata_allow_list():
    data = labels(extract_source_metadata("product_hunt", {"tagline":"Tiny tool", "topics":["Productivity"], "votes":42}))
    assert data["Tagline"] == "Tiny tool" and data["Topics"] == "Productivity"


def test_yanko_metadata_allow_list():
    data = labels(extract_source_metadata("yanko_design", {"categories":["Product Design"], "published_at":"2026-08-26"}))
    assert data["Category"] == "Product Design" and data["Published"] == "2026-08-26"


def test_source_metadata_does_not_expose_raw_dictionary():
    metadata = extract_source_metadata("amazon", {"price":"$10", "GEMINI_API_KEY":"hidden", "raw_html":"<secret>"})
    rendered = repr(metadata)
    assert "GEMINI_API_KEY" not in rendered and "raw_html" not in rendered


def test_english_only_ai_has_one_pending_state_and_no_generic_chinese():
    content = chinese_ai_content(None, None, [])
    assert content.pending is True
    assert content.primary_reason == content.key_opportunity == ""
    assert content.main_risks == ()


def test_real_chinese_ai_is_preferred_without_rewriting():
    content = chinese_ai_content("真实理由", "真实机会", ["真实风险"])
    assert content.pending is False
    assert content.primary_reason == "真实理由"
    assert content.key_opportunity == "真实机会"
    assert content.main_risks == ("真实风险",)
