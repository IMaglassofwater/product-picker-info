"""Phase 11H.1B conservative Reddit identity regression tests."""

from evidence_foundation import classify_eligibility, normalize_identity, normalize_reddit_title
from models import Product


def reddit(title: str, body: str) -> Product:
    return Product(
        project_id="r1", source_platform="reddit_arctic_shift",
        url="https://www.reddit.com/r/test/comments/r1/post/", title=title,
        description=body, category="test", image_url="https://example.test/image.jpg",
        raw_data={"permalink": "/r/test/comments/r1/post/"},
    )


def identity(title: str, body: str):
    value = reddit(title, body)
    return normalize_identity(value, classify_eligibility(value))


def test_manual_winkbed_identity_and_chinese_name_preserve_source_title():
    title = "WinkBed Luxury Firm failed in under 4 years despite 20+ year durability claims"
    result = identity(title, "I bought this WinkBed Luxury Firm mattress and used it for under four years.")
    assert result.source_title == title
    assert result.normalized_product_name == "WinkBed Luxury Firm Mattress"
    assert result.normalized_product_name_zh == "WinkBed Luxury Firm 床垫"
    assert result.confidence == "HIGH"


def test_manual_polywood_uses_body_product_category_not_generic_product():
    result = identity("So here’s my Polywood shout-out", "I bought two POLYWOOD outdoor rocking chairs and one rocker failed.")
    assert result.normalized_product_name == "POLYWOOD Outdoor Rocking Chair"
    assert result.normalized_product_name_zh == "POLYWOOD 户外摇椅"


def test_manual_otterbox_extracts_concrete_phone_case():
    result = identity("OtterBox warranty replacement, good karma coming back to me", "I used an OtterBox Defender phone case until it broke.")
    assert result.normalized_product_name == "OtterBox Phone Case"
    assert result.normalized_product_name_zh == "OtterBox 手机壳"


def test_manual_kelty_extracts_tent_without_translating_discussion_sentence():
    title = "Does Kelty Suck Now?"
    result = identity(title, "I own and used two Kelty tents; a fiberglass pole failed.")
    assert result.normalized_product_name == "Kelty Tent"
    assert result.normalized_product_name_zh == "Kelty 帐篷"
    assert result.normalized_product_name_zh != "Kelty现在很差吗？"
    assert result.source_title == title


def test_unresolved_discussion_sentence_has_no_fabricated_identity_or_translation():
    title = "What happened here and what should I do?"
    result = identity(title, "A vague discussion mentioning several unrelated things.")
    assert normalize_reddit_title(title, "") is None
    assert result.source_title == title
    assert result.normalized_product_name is None
    assert result.normalized_product_name_zh is None
    assert result.confidence == "LOW"
