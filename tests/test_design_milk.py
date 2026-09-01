import xml.etree.ElementTree as ET

from evidence_foundation import classify_concrete_product, classify_eligibility, normalize_identity
from scrapers.design_milk import DesignMilkScraper


def entry(title):
    return ET.fromstring(f"""<item><title>{title}</title><link>https://design-milk.com/item</link>
    <description><![CDATA[<p>A modular desk lamp for small spaces.</p><img src='https://img.example/lamp.jpg'>]]></description>
    <category>Product Design</category><pubDate>Mon, 01 Jan 2026 00:00:00 GMT</pubDate></item>""")


def test_design_milk_concrete_object():
    item = DesignMilkScraper(access_enabled=True)._parse_entry(entry("A Modular Desk Lamp for Small Spaces"))
    eligibility = classify_eligibility(item)
    assert eligibility.content_type == "PRODUCT_DESIGN"
    assert classify_concrete_product(item, eligibility).status == "CONCRETE"
    assert normalize_identity(item, eligibility).normalized_product_name == "Desk Lamp"


def test_design_milk_roundup_is_excluded():
    item = DesignMilkScraper(access_enabled=True)._parse_entry(entry("10 Best Lamps We Love This Year"))
    assert classify_eligibility(item).eligibility_status == "INELIGIBLE"


def test_design_milk_is_deferred_after_final_probe():
    import pytest
    from scrapers.base_scraper import ScraperFetchError
    with pytest.raises(ScraperFetchError, match="DEFERRED"):
        DesignMilkScraper().fetch()
