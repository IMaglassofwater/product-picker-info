"""Free rule-based gate for actionable physical product specificity."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal


SpecificityStatus = Literal["SPECIFIC", "REVIEW", "TOO_BROAD"]


@dataclass(frozen=True)
class SpecificityResult:
    specificity_status: SpecificityStatus
    specificity_score: int
    specificity_reason: str
    specificity_flags: list[str]


PRODUCT_PATTERNS = {
    "fanny_pack": ("fanny pack", "waist pack"),
    "key_organizer": ("key organiser", "key organizer", "key holder"),
    "journal": ("journal", "notebook"),
    "camping_pillow": ("backpacking pillow", "camping pillow", "travel pillow"),
    "manual_can_opener": ("manual can opener", "can opener"),
    "wallet": ("wallet",),
    "organizer": ("organizer", "organiser"),
    "backpack": ("backpack", "rucksack"),
    "duffle": ("duffle", "duffel"),
    "sleeping_bag": ("sleeping bag",),
    "water_bottle": ("water bottle", "waterbottle"),
    "pocket_clip": ("pocket clip",),
    "pouch": ("pouch",),
    "packing_cube": ("packing cube",),
    "lamp": ("desk lamp", "lamp"),
}

FEATURE_PHRASES = (
    "without zipper", "no zipper", "specific requirements", "too expensive",
    "must be stored compressed", "different key", "flat key", "rounded key",
    "side sleeper", "doesn't slide", "does not slide", "hard to", "difficult",
    "too heavy", "too bulky", "not enough", "problem", "pain point",
)
REQUIREMENT_PHRASES = (
    "up to ", "at least ", "under ", "over ", " litre", " liter", "l or above",
    "compact", "lightweight", "specific", "size", "material", "capacity",
    "for airplane", "for work", "side sleeper", "compressed",
)
IMPROVEMENT_PHRASES = (
    "without", "alternative", "improve", "better", "opening", "closure",
    "storage", "layout", "ergonomic", "portable", "attachment", "organize",
    "organise", "made it myself", "diy", "non-slip", "strap",
)
BROAD_PHRASES = {
    "packing_advice": ("packing and bag advice", "packing advice"),
    "trip_planning": ("trip coming up", "trip planning", "what to pack"),
    "unspecified_edc_request": ("adding an edc item", "taking suggestions"),
    "setup_optimization": ("optimize my setup", "rate my setup"),
    "gear_list_review": ("gear list", "packing list review"),
    "general_recommendation": ("recommend me something", "what should i buy"),
}

POSITIVE_SIGNAL_MAP = {
    "clear_feature_gap": "explicit_feature_request",
    "clear_size_requirement": "explicit_size_requirement",
    "clear_usage_scenario": "explicit_usage_scenario",
    "storage_or_organization": "explicit_storage_requirement",
    "portability_problem": "explicit_portability_problem",
    "accessibility_problem": "explicit_feature_request",
    "appearance_positioning_gap": "explicit_appearance_gap",
    "simple_material_change": "explicit_material_requirement",
    "low_tech_modification": "clear_improvement_direction",
    "existing_simple_product": "clear_existing_product",
}


def assess_specificity(
    title: str,
    description: str,
    signals: list[str],
    candidate_type: str,
    source_platform: str = "",
) -> SpecificityResult:
    """Assess whether existing evidence identifies one actionable product opportunity."""
    text = " ".join(f"{title} {description}".casefold().split())
    flags: list[str] = []
    products = [
        family for family, phrases in PRODUCT_PATTERNS.items()
        if any(phrase in text for phrase in phrases)
    ]
    if products:
        flags.append("explicit_product_type")
    if len(products) > 1:
        flags.append("multiple_product_families")
    signal_flags = {POSITIVE_SIGNAL_MAP[signal] for signal in signals if signal in POSITIVE_SIGNAL_MAP}
    flags.extend(sorted(signal_flags))
    if any(phrase in text for phrase in FEATURE_PHRASES):
        flags.append("explicit_feature_request")
    if any(phrase in text for phrase in REQUIREMENT_PHRASES):
        flags.append("explicit_requirement")
    if any(phrase in text for phrase in IMPROVEMENT_PHRASES):
        flags.append("clear_improvement_direction")
    if "made it myself" in text or "leathercraft" in text or "diy" in text:
        flags.append("DIY_workaround")
    if "too expensive" in text or "price" in text or "budget" in text:
        flags.append("explicit_price_pain")
    broad = [
        name for name, phrases in BROAD_PHRASES.items()
        if any(phrase in text for phrase in phrases)
    ]
    flags.extend(broad)
    flags = list(dict.fromkeys(flags))

    product = "explicit_product_type" in flags
    gap = "explicit_feature_request" in flags or "explicit_price_pain" in flags
    improvement = "clear_improvement_direction" in flags or "DIY_workaround" in flags
    requirement = any(flag.startswith("explicit_") and flag not in {
        "explicit_product_type", "explicit_feature_request", "explicit_price_pain"
    } for flag in flags)
    score = 30 * product + 20 * gap + 20 * improvement + 15 * requirement
    score += 10 * ("explicit_usage_scenario" in flags)
    score += 5 * ("clear_existing_product" in flags)
    score -= min(30, 15 * len(broad))
    score -= 10 * ("multiple_product_families" in flags and not gap)
    score = max(0, min(100, score))

    if candidate_type != "demand_opportunity":
        if product:
            return SpecificityResult(
                "SPECIFIC", max(70, score),
                "Explicit physical product; existing candidate type remains eligible for actionability review.",
                flags,
            )
        return SpecificityResult(
            "REVIEW", max(45, score),
            "Existing non-demand candidate lacks a clearly extracted product family; review actionability.",
            flags,
        )

    if broad and not (product and gap):
        return SpecificityResult(
            "TOO_BROAD", min(39, score),
            "General advice or planning request without one product family and a specific feature gap.",
            flags,
        )
    if product and gap and (improvement or requirement):
        return SpecificityResult(
            "SPECIFIC", max(65, score),
            "Single product family, explicit problem, and a researchable improvement direction are present.",
            flags,
        )
    if product and (gap or requirement or improvement):
        return SpecificityResult(
            "REVIEW", max(40, min(64, score)),
            "Product family is identifiable, but the feature gap or improvement direction needs clarification.",
            flags,
        )
    if not product and requirement and improvement:
        return SpecificityResult(
            "REVIEW", max(40, min(59, score)),
            "The need and use context are explicit, but multiple product families could solve it.",
            flags,
        )
    return SpecificityResult(
        "TOO_BROAD", min(39, score),
        "No single product family plus specific problem or feature gap can be extracted.",
        flags,
    )
