"""Tests for the free Final Opportunity Specificity Gate."""

from opportunity_specificity import assess_specificity


def _assess(title, description, signals=None, candidate_type="demand_opportunity"):
    return assess_specificity(title, description, signals or [], candidate_type, "reddit")


def test_zipperless_fanny_pack_is_specific():
    result = _assess("Fanny pack without zipper", "A work pocket with an opening that avoids zippers.", ["clear_feature_gap", "clear_usage_scenario"])
    assert result.specificity_status == "SPECIFIC"


def test_key_organizer_with_requirements_is_specific():
    result = _assess("Looking for key organiser", "Needs flat and rounded keys, up to 10 keys.", ["clear_size_requirement", "storage_or_organization", "clear_feature_gap"])
    assert result.specificity_status == "SPECIFIC"


def test_diy_leather_journal_price_pain_is_specific():
    result = _assess("My", "PaperRepublic was too expensive, so I got into leathercraft and made a journal myself.")
    assert result.specificity_status == "SPECIFIC"
    assert "DIY_workaround" in result.specificity_flags


def test_generic_packing_advice_and_unspecified_edc_are_too_broad():
    packing = _assess("Packing and bag advice for 8 day Swiss Alps trip", "Help with my packing list and trip planning.")
    edc = _assess("Considering adding an EDC item, taking suggestions", "What should I buy?")
    assert packing.specificity_status == "TOO_BROAD"
    assert edc.specificity_status == "TOO_BROAD"


def test_ambiguous_travel_storage_is_review():
    result = _assess("Compact travel storage", "Need compact storage for cables when traveling.", ["clear_usage_scenario", "storage_or_organization"])
    assert result.specificity_status == "REVIEW"


def test_size_and_feature_gap_increase_specificity():
    base = _assess("Travel pouch", "Need something for travel.")
    detailed = _assess("Travel pouch", "Need a compact pouch under 20 cm without a zipper.", ["clear_size_requirement", "clear_feature_gap"])
    assert detailed.specificity_score > base.specificity_score
    assert detailed.specificity_status == "SPECIFIC"


def test_explicit_amazon_and_validated_products_are_not_too_broad():
    amazon = _assess("Manual can opener", "Stainless steel manual can opener.", [], "consumer_trend")
    validated = _assess("Camping pillow", "Existing lightweight camping pillow.", [], "validated_product")
    assert amazon.specificity_status == "SPECIFIC"
    assert validated.specificity_status == "SPECIFIC"
