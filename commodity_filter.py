"""Rule-based commodity and red-ocean screening for simple products."""

from dataclasses import dataclass
from typing import Literal

from models import Product


CommodityStatus = Literal["PROMISING", "REVIEW", "COMMODITY"]


@dataclass(frozen=True)
class CommodityResult:
    commodity_status: CommodityStatus
    commodity_score: int
    commodity_reason: str
    commodity_flags: list[str]


def filter_commodity(product: Product) -> CommodityResult:
    """Evaluate explicit differentiation without using rank, ratings, or reviews."""
    text = f"{product.title} {product.description}".casefold()
    flags: list[str] = []

    if any(term in text for term in ("10x10", "large shelter", "oversized item", "large furniture")):
        flags.extend(("bulky_shipping", "highly_mature_category"))
        return CommodityResult(
            "COMMODITY", 10,
            "large or bulky mature product without a clear lightweight innovation case",
            flags,
        )

    mature_groups = (
        ("generic_bath_mat", ("bath mat", "bathroom rug")),
        ("generic_drinkware", ("tumbler", "water bottle", "cup")),
        ("generic_lunch_box", ("lunch box", "lunch bag")),
        ("generic_kitchen_tool", ("can opener",)),
        ("generic_container", ("mason jar", "oats container", "food container")),
        ("generic_storage", ("storage box", "storage bin", "organizer tray")),
        ("generic_bag", ("basic bag", "tote bag")),
        ("generic_home_accessory", ("home decor accessory",)),
    )
    for flag, terms in mature_groups:
        if any(term in text for term in terms):
            flags.append(flag)
    if flags:
        flags.append("highly_mature_category")

    innovation_groups = (
        ("modular_design", ("modular", "interchangeable module")),
        ("foldable", ("foldable", "collapsible")),
        ("space_saving", ("space-saving", "space saving")),
        ("opening_mechanism", ("flip lid", "built-in straw", "zipper-free", "one-touch opening")),
        ("portable_design", ("portable", "packable")),
        ("specific_user_segment", ("for seniors", "for children", "one-handed users")),
        ("material_change", ("recycled nylon", "plant-based material")),
        ("multi_function", ("multifunctional", "multi-functional", "2-in-1", "3-in-1")),
        ("size_innovation", ("ultra compact", "extra slim", "adjustable size")),
        ("storage_innovation", ("stackable system", "portion system", "modular storage")),
        ("cleaning_improvement", ("self-cleaning", "removable washable liner")),
        ("accessibility_improvement", ("one-handed", "easy grip")),
        ("ergonomic_improvement", ("oversized knob", "ergonomic handle", "comfortable handle")),
        ("structural_innovation", ("transformable", "patented structure")),
        ("specific_use_case", ("cupholder compatible", "overnight oats")),
    )
    innovations = [
        flag for flag, terms in innovation_groups if any(term in text for term in terms)
    ]
    flags.extend(flag for flag in innovations if flag not in flags)

    strong = {
        "modular_design", "foldable", "space_saving", "structural_innovation",
        "accessibility_improvement", "ergonomic_improvement", "storage_innovation",
    }
    strong_count = len(strong.intersection(innovations))
    score = min(100, 25 + 20 * strong_count + 8 * (len(innovations) - strong_count))
    if strong_count >= 1 and len(innovations) >= 2:
        return CommodityResult(
            "PROMISING", max(70, score),
            "explicit product differentiation is present beyond market popularity",
            flags,
        )
    if innovations:
        return CommodityResult(
            "REVIEW", max(40, score),
            "some differentiation signals are present, but public listing text is insufficient",
            flags,
        )
    if flags:
        return CommodityResult(
            "COMMODITY", 20,
            "mature consumer category with no explicit differentiation in current text",
            flags,
        )
    return CommodityResult(
        "REVIEW", 35,
        "current title and description do not establish either innovation or commodity status",
        [],
    )
