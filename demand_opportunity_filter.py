"""Rule-based productization pre-filter for validated demand signals."""

from dataclasses import dataclass
import re
from typing import Literal

from demand_signal_filter import DemandSignalResult
from models import Product


DemandOpportunityStatus = Literal["PRODUCTIZABLE", "REVIEW", "NOT_FIT"]

HARD_NOT_FIT_PATTERNS = {
    "large_or_heavy_product": (
        r"\brefrigerator\b", r"\bfridge\b", r"\blarge appliance\b",
        r"\blarge furniture\b", r"\bwashing machine\b", r"\bfreezer\b",
    ),
    "complex_electronics": (
        r"\bbattery backup\b", r"\bbattery back up\b", r"\bpower station\b",
        r"\belectronic cooler\b", r"\bsmart device\b", r"\bcamera\b",
        r"\bcomputer hardware\b", r"\bjump starter\b", r"\bcar fridge\b",
    ),
    "high_regulation": (
        r"\bmedical\b", r"\bmedicine\b", r"\bdrug\b", r"\bsupplement\b",
        r"\bfood product\b", r"\bcosmetic\b", r"\btreatment\b",
    ),
}

TECHNICAL_REVIEW_PATTERNS = {
    "technical_footwear_or_apparel": (
        r"\btechnical running shoes?\b", r"\btrail running shoes?\b",
        r"\bperformance footwear\b", r"\btechnical jacket\b",
        r"\bwinter jacket\b",
    ),
    "complex_outdoor_equipment": (
        r"\btents?\b", r"\bsleeping system\b", r"\btechnical stove\b",
        r"\bcamping stove\b",
    ),
    "multi_product_problem": (
        r"\boptimi[sz]e .{0,20}(?:onebag|one-bag) setup\b",
        r"\bpacking list\b", r"\bgear list\b",
    ),
}

FLAG_PATTERNS = {
    "existing_simple_product": (
        r"\bbag\b", r"\bfanny pack\b", r"\bcrossbody\b", r"\bpouch\b",
        r"\borganizer\b", r"\borganiser\b", r"\bholder\b", r"\bstand\b",
        r"\bwallet\b", r"\bbackpack\b", r"\bclip\b",
        r"\bstorage accessory\b", r"\btravel accessory\b",
        r"\bpet accessory\b", r"\bdesk accessory\b", r"\bleather journal\b",
        r"\bkey organi[sz]er\b",
    ),
    "clear_feature_gap": (
        r"\bwithout (?:a )?zipper\b", r"\bzipper[- ]free\b",
        r"\bspecific requirements?\b", r"\bflat and rounded keys\b",
        r"\bflat \+ rounded keys\b", r"\blaptop organi[sz]ation\b",
        r"\b(?:internal )?compartments?\b", r"\bneeds? to (?:fit|hold|carry|work)\b",
    ),
    "clear_usage_scenario": (
        r"\bat work\b", r"\bwork backpack\b", r"\boffice\b",
        r"\bdog walking\b", r"\btravel\b", r"\bdaily (?:work|use)\b",
        r"\blaptop\b", r"\bcar camping\b",
    ),
    "clear_size_requirement": (
        r"\b\d+(?:\.\d+)?[ -]?(?:l|liters?|inches?|inch|cm|mm)\b",
        r"[><]\s*\d+", r"\bup to \d+\b", r"\b\d+[- ]keys?\b",
        r"\bwaist (?:strap|band).{0,20}\d+\b",
    ),
    "clear_price_pain": (
        r"\btoo expensive\b", r"\bcheaper\b", r"\bcan(?:not|'t) afford\b",
        r"\bunder (?:a budget|\$|\u00a3|\u20ac|\d)\b",
    ),
    "low_tech_modification": (
        r"\bwithout (?:a )?zipper\b", r"\bzipper[- ]free\b",
        r"\bnon[- ]tactical\b", r"\bnot tactical\b", r"\bnot hiking\b",
        r"\bflat and rounded keys\b", r"\bspecific dimensions?\b",
        r"\bcompartments?\b", r"\bsleeve\b",
    ),
    "storage_or_organization": (
        r"\bstorage\b", r"\borgani[sz](?:e|er|ation)\b", r"\bpockets?\b",
        r"\bcompartments?\b", r"\bdrawer\b", r"\bshelf\b",
    ),
    "portability_problem": (
        r"\blightweight\b", r"\bcompact\b", r"\bportable\b",
        r"\bcarry\b", r"\bonebag\b", r"\bone-bag\b",
    ),
    "accessibility_problem": (
        r"\bquick (?:access|reach)\b", r"\beasy[- ]access\b",
        r"\breach for often\b", r"\bwithout (?:a )?zipper\b",
        r"\bzipper[- ]free\b",
    ),
    "appearance_positioning_gap": (
        r"\bprofessional\b", r"\bnon[- ]tactical\b", r"\bnot tactical\b",
        r"\bdoesn(?:'t| not) (?:look|feel) like .{0,20}(?:hiking|tactical)\b",
    ),
    "DIY_workaround": (
        r"\bmade (?:one|it) (?:myself|personally)\b", r"\bDIY\b",
    ),
    "simple_material_change": (
        r"\bleather\b", r"\bnylon\b", r"\bpolyester\b", r"\bfabric\b",
        r"\bABS\b", r"\bsilicone\b",
    ),
}


@dataclass(frozen=True)
class DemandOpportunityResult:
    """Suitability of a demand for low-cost physical micro-innovation research."""

    demand_opportunity_status: DemandOpportunityStatus
    demand_opportunity_score: int
    demand_opportunity_reason: str
    opportunity_flags: list[str]


def filter_demand_opportunity(
    product: Product,
    demand_signal: DemandSignalResult,
) -> DemandOpportunityResult:
    """Assess productizability without claiming supplier or cost validation."""
    text = " ".join((product.title, product.description, product.category))
    flags = [
        name for name, patterns in FLAG_PATTERNS.items() if _matches(text, patterns)
    ]
    hard_risks = [
        name
        for name, patterns in HARD_NOT_FIT_PATTERNS.items()
        if _matches(text, patterns)
    ]
    if hard_risks:
        return DemandOpportunityResult(
            "NOT_FIT",
            max(0, 25 - 5 * len(hard_risks)),
            "not fit risks: " + ", ".join(hard_risks),
            flags,
        )

    review_risks = [
        name
        for name, patterns in TECHNICAL_REVIEW_PATTERNS.items()
        if _matches(text, patterns)
    ]
    score = min(100, 35 + 9 * len(flags))
    supporting_flags = [flag for flag in flags if flag != "existing_simple_product"]

    if (
        "existing_simple_product" in flags
        and len(supporting_flags) >= 2
        and not review_risks
    ):
        return DemandOpportunityResult(
            "PRODUCTIZABLE",
            max(70, score),
            (
                "existing simple product with specific low-tech improvement signals; "
                "suitable for supplier and micro-innovation research; supplier and "
                "cost not yet verified"
            ),
            flags,
        )

    reason = (
        "implementation complexity requires review: " + ", ".join(review_risks)
        if review_risks
        else "real demand, but a specific low-complexity product solution is unclear"
    )
    if demand_signal.signal_status == "HIGH":
        reason += "; high demand strength does not override productization fit"
    return DemandOpportunityResult("REVIEW", min(69, score), reason, flags)


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
