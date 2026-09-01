from evidence_foundation import classify_concrete_product, classify_eligibility, normalize_identity
from scrapers.hacker_news import HackerNewsScraper


def test_show_hn_product_is_concrete_software():
    item = HackerNewsScraper()._parse_item({
        "id": 42,
        "title": "Show HN: I built TidyCSV — an open-source tool for cleaning CSV files",
        "url": "https://tidycsv.example",
        "score": 55,
        "descendants": 12,
        "time": 123456,
        "by": "maker",
    })
    eligibility = classify_eligibility(item)
    assert eligibility.content_type == "SOFTWARE_PRODUCT"
    assert classify_concrete_product(item, eligibility).status == "CONCRETE"
    assert normalize_identity(item, eligibility).normalized_product_name == "TidyCSV"
    assert item.raw_data["points"] == 55


def test_generic_hn_discussion_is_not_eligible_product():
    item = HackerNewsScraper()._parse_item({
        "id": 43, "title": "Show HN: Thoughts about the software industry",
        "score": 1, "descendants": 0,
    })
    assert classify_eligibility(item).eligibility_status == "INELIGIBLE"


def test_show_hn_external_product_url_is_sufficient_factual_product_signal():
    item = HackerNewsScraper()._parse_item({
        "id": 44, "title": "Show HN: TidyCSV", "url": "https://tidycsv.example",
        "score": 2, "descendants": 0,
    })
    assert classify_eligibility(item).eligibility_status == "ELIGIBLE"


def test_show_hn_sentence_identity_cleanup_is_deterministic():
    cases = {
        "Show HN: I missed the moving blocks, so I built a real Linux disk defragmenter": "Linux Disk Defragmenter",
        "Show HN: Drop a SQL schema, get an interactive ER diagram": "Interactive SQL ER Diagram Tool",
        "Show HN: My startup-idea scanner scored 500 ideas; the best got 6.3/10": "Startup Idea Scanner",
        "Show HN: Prove your code produced your claims without making reviewers rerun it": "Code Claim Verification Tool",
    }
    for index, (title, expected) in enumerate(cases.items(), 50):
        item = HackerNewsScraper()._parse_item({"id": index, "title": title, "url": "https://tool.example"})
        eligibility = classify_eligibility(item)
        assert normalize_identity(item, eligibility).normalized_product_name == expected
