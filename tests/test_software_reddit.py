from evidence_foundation import classify_concrete_product, classify_eligibility, normalize_reddit_title
from models import Product
from scrapers.software_reddit import SoftwareRedditScraper
from scrapers.arctic_shift import ArcticShiftScraper


def product(title, description="One specific product request"):
    return Product("r1", "reddit_software", "https://reddit.com/r/x/1", title,
                   description, "productivity", "https://reddit.com/icon.png", {})


def test_selected_subreddits_are_bounded_and_product_focused():
    scraper = SoftwareRedditScraper()
    assert isinstance(scraper, ArcticShiftScraper)
    assert scraper.subreddits == ("SideProject", "selfhosted", "opensource", "productivity")


def test_concrete_single_product_requests_are_preserved_and_normalized():
    expected = {
        "Seeking advice for garbage bags": "Garbage Bags",
        "Advice on cot for a tent?": "Camping Tent Cot",
        "Budget duffle/backpack @ 40l or above": "40L+ Convertible Duffel Backpack",
        "BIFL Comfortable Men's Tennis Shoes": "Durable Comfortable Men's Tennis Shoes",
    }
    for title, name in expected.items():
        item = product(title)
        eligibility = classify_eligibility(item)
        assert normalize_reddit_title(title) == name
        assert classify_concrete_product(item, eligibility).status == "CONCRETE"


def test_multi_product_comparison_remains_non_concrete():
    item = product("I compared 10 travel bags")
    eligibility = classify_eligibility(item)
    assert classify_concrete_product(item, eligibility).status == "NON_CONCRETE"


def test_concrete_software_need_normalization_and_broad_recommendation_exclusion():
    needs = {
        "Looking for a simple local-first expense tracker": "Local-First Expense Tracker",
        "Need a browser extension that blocks Shorts": "Shorts-Blocking Browser Extension",
        "Does anyone know a self-hosted alternative to Notion?": "Self-Hosted Workspace / Knowledge App",
        "Looking for an app to organize screenshots": "Screenshot Organizer App",
        "I built a tiny tool for cleaning CSV files": "CSV Cleaning Tool",
    }
    for title, expected in needs.items():
        assert normalize_reddit_title(title) == expected
    broad = product("Best productivity tools?")
    assert classify_concrete_product(broad, classify_eligibility(broad)).status == "NON_CONCRETE"


def test_one_software_subreddit_failure_does_not_block_others(monkeypatch):
    scraper = SoftwareRedditScraper(subreddits=("SideProject", "selfhosted"), limit_per_subreddit=2)
    def fake_fetch(subreddit, query):
        from scrapers.base_scraper import ScraperFetchError
        if subreddit == "SideProject":
            raise ScraperFetchError("blocked")
        return [{
            "id": "ok1", "title": "I built a local-first app", "selftext": "open source tool",
            "subreddit": subreddit, "permalink": "/r/selfhosted/comments/ok1/x/",
            "score": 5, "num_comments": 2,
        }]
    monkeypatch.setattr(scraper, "_fetch_subreddit", fake_fetch)
    products = scraper.fetch()
    assert products and {p.category for p in products} == {"selfhosted"}
    assert "SideProject" in scraper.failures


def test_moderator_removed_and_troubleshooting_records_are_excluded():
    assert SoftwareRedditScraper._has_valid_text({
        "title": "[ Removed by moderator ]", "selftext": "app", "url": "https://reddit.test/x"
    }) is False
    trouble = product("Bazarr provider throwing 403 Forbidden - bypass seems broken")
    assert classify_concrete_product(trouble, classify_eligibility(trouble)).status == "NON_CONCRETE"


def test_software_reddit_defaults_to_software_and_ambiguous_identity_is_low_confidence():
    from evidence_foundation import normalize_identity
    item = product("PULS: Unified System Monitoring & Management Tool for Linux")
    eligibility = classify_eligibility(item)
    assert eligibility.content_type == "SOFTWARE_PRODUCT"
    identity = normalize_identity(item, eligibility)
    assert identity.normalized_product_name == "PULS Linux System Monitoring Tool"
    vague = product("A named but sentence-form launch that has no safe rewrite")
    vague_identity = normalize_identity(vague, classify_eligibility(vague))
    assert vague_identity.source_title == "A named but sentence-form launch that has no safe rewrite"
    assert vague_identity.normalized_product_name is None
    assert vague_identity.confidence == "LOW"
    assert vague_identity.confidence == "LOW"
