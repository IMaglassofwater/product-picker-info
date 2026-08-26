"""Free rules for routing creative-design content into inspiration research."""

from dataclasses import dataclass
from typing import Literal

from models import Product


CreativeContentType = Literal[
    "physical_product",
    "concept_product",
    "architecture",
    "vehicle",
    "technology_complex",
    "other",
]


@dataclass(frozen=True)
class CreativeContentResult:
    """Classification and low-budget feasibility evidence for one article."""

    content_type: CreativeContentType
    eligible: bool
    feasibility_score: int
    information_clarity_score: int
    micro_innovation_score: int
    signals: list[str]
    risk_flags: list[str]
    reason: str


ARCHITECTURE_TERMS = {
    "architecture", "architect", "building", "interior", "pavilion",
    "residence", "house", "cabin", "tower", "hotel", "museum", "gallery",
}
VEHICLE_TERMS = {
    "automotive", "vehicle", "car", "motorcycle", "scooter", "camper",
    "trailer", "aircraft", "yacht",
}
COMPLEX_TECH_TERMS = {
    "robot", "robotics", "smartphone", "laptop", "computer", "processor",
    "artificial intelligence", "3d printer", "vr", "virtual reality",
    "wireless earbuds", "bluetooth", "battery", "electric vehicle",
}
PHYSICAL_TERMS = {
    "product design", "furniture", "lighting", "lamp", "backpack", "bag",
    "organizer", "organiser", "storage", "bottle", "wallet", "pouch",
    "accessory", "accessories", "tool", "stationery", "kitchen", "home",
    "fashion", "toy", "toys", "chair", "container", "holder", "case",
    "packaging",
}
LARGE_PRODUCT_TERMS = {
    "armchair", "sofa", "couch", "dining table", "wardrobe", "cabinet",
    "large furniture", "appliance", "refrigerator", "trailer",
}


def filter_creative_content(product: Product) -> CreativeContentResult:
    """Classify creative content and enforce low-budget inspiration criteria."""
    categories = _strings(product.raw_data.get("categories"))
    tags = _strings(product.raw_data.get("tags"))
    title_text = product.title.casefold()
    body_text = " ".join([product.title, product.description]).casefold()
    category_text = " ".join(
        [product.category, *categories, *tags]
    ).casefold()
    text = f"{body_text} {category_text}"

    content_type = _classify(text, title_text, category_text)
    signals = _signals(text, content_type)
    risks = _risks(text, content_type)
    feasibility_score = _feasibility_score(signals, risks)
    micro_score = _micro_score(signals)
    clarity_score = _clarity_score(product, categories or tags)
    eligible = (
        content_type in {"physical_product", "concept_product"}
        and not risks
        and len(signals) >= 2
        and feasibility_score >= 60
        and micro_score >= 45
    )

    if content_type not in {"physical_product", "concept_product"}:
        reason = f"{content_type} content is outside inspiration candidate scope"
    elif risks:
        reason = "excluded by personal-resource hard risks: " + ", ".join(risks)
    elif not eligible:
        reason = "insufficient low-cost micro-innovation evidence in public RSS data"
    else:
        reason = (
            "simple creative product with multiple low-cost micro-innovation "
            "signals; supplier, cost, and demand remain unvalidated"
        )
    return CreativeContentResult(
        content_type=content_type,
        eligible=eligible,
        feasibility_score=feasibility_score,
        information_clarity_score=clarity_score,
        micro_innovation_score=micro_score,
        signals=signals,
        risk_flags=risks,
        reason=reason,
    )


def _classify(
    text: str, title_text: str, category_text: str
) -> CreativeContentType:
    if _contains(category_text, ARCHITECTURE_TERMS) or _contains(
        title_text, ARCHITECTURE_TERMS
    ):
        return "architecture"
    if _contains(category_text, VEHICLE_TERMS) or _contains(
        title_text, VEHICLE_TERMS
    ):
        return "vehicle"
    if _contains(text, COMPLEX_TECH_TERMS) or any(
        term in category_text
        for term in (
            "technology", "wearable", "audio", "gaming", "gadgets",
            "robotics", "appliances",
        )
    ):
        return "technology_complex"
    physical = _contains(text, PHYSICAL_TERMS)
    if physical and any(
        term in text
        for term in (
            "concept", "conceptual", "prototype", "imagines", "lego ideas",
        )
    ):
        return "concept_product"
    if physical:
        return "physical_product"
    return "other"


def _signals(text: str, content_type: CreativeContentType) -> list[str]:
    signals: list[str] = []
    if content_type in {"physical_product", "concept_product"}:
        signals.append("existing_simple_product")
    if not _contains(text, COMPLEX_TECH_TERMS) and any(
        term in text
        for term in ("simple", "manual", "non-electronic", "low-tech", "mechanical")
    ):
        signals.append("low_tech_modification")
    mappings = (
        ("storage_or_organization", ("storage", "organizer", "organiser", "pocket", "compartment")),
        ("portability_problem", ("portable", "carry", "travel", "packable", "backpack", "bag")),
        ("simple_material_change", ("material", "fabric", "leather", "wood", "plastic", "metal", "recycled")),
        ("compact_design", ("compact", "small", "mini", "foldable", "pocket-size")),
        ("modular_design", ("modular", "module", "interchangeable")),
        ("multi_use_design", ("multi-use", "multifunction", "multi-function", "2-in-1", "3-in-1")),
        ("space_saving", ("space-saving", "space saving", "folds flat", "collapsible")),
        ("accessibility_improvement", ("easy access", "accessible", "one-handed", "cord problem")),
        ("everyday_use", ("everyday", "daily", "desk", "home", "work", "travel")),
        ("simple_mechanical_design", ("hinge", "clip", "buckle", "mechanical", "manual")),
    )
    for signal, terms in mappings:
        if any(term in text for term in terms):
            signals.append(signal)
    return list(dict.fromkeys(signals))


def _risks(text: str, content_type: CreativeContentType) -> list[str]:
    risks: list[str] = []
    if content_type == "architecture":
        risks.append("architecture")
    if content_type == "vehicle":
        risks.append("vehicle")
    if content_type == "technology_complex":
        risks.append("complex_electronics")
    if _contains(text, LARGE_PRODUCT_TERMS):
        risks.append("large_or_heavy")
    return list(dict.fromkeys(risks))


def _feasibility_score(signals: list[str], risks: list[str]) -> int:
    score = 42
    weights = {
        "existing_simple_product": 10,
        "low_tech_modification": 10,
        "storage_or_organization": 7,
        "portability_problem": 7,
        "simple_material_change": 6,
        "compact_design": 8,
        "modular_design": 5,
        "multi_use_design": 5,
        "space_saving": 7,
        "accessibility_improvement": 6,
        "everyday_use": 7,
        "simple_mechanical_design": 7,
    }
    score += sum(weights.get(signal, 0) for signal in signals)
    score -= 60 * len(risks)
    return max(0, min(100, score))


def _micro_score(signals: list[str]) -> int:
    weights = {
        "existing_simple_product": 5,
        "low_tech_modification": 13,
        "storage_or_organization": 10,
        "portability_problem": 8,
        "simple_material_change": 10,
        "compact_design": 10,
        "modular_design": 13,
        "multi_use_design": 12,
        "space_saving": 12,
        "accessibility_improvement": 12,
        "everyday_use": 6,
        "simple_mechanical_design": 12,
    }
    return min(100, 24 + sum(weights.get(signal, 0) for signal in signals))


def _clarity_score(product: Product, categories: list[str]) -> int:
    score = 20 if product.title.strip() else 0
    score += 40 if len(product.description.strip()) >= 60 else 20
    score += 20 if categories else 0
    score += 10 if product.raw_data.get("published_at") else 0
    score += 10 if product.raw_data.get("image_url") else 0
    return min(100, score)


def _contains(text: str, terms: set[str]) -> bool:
    padded = f" {text} "
    return any(
        term in text if " " in term or "-" in term else f" {term} " in padded
        for term in terms
    )


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []
