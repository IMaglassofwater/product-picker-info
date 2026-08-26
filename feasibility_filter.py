"""Rule-based personal seller feasibility calibration."""

from dataclasses import dataclass
import re
from typing import Literal

from models import Product


FeasibilityStatus = Literal["PASS", "REVIEW", "REJECT"]

RISK_PATTERNS = {
    "weapon_or_blade": ("knife", "blade", "axe", "weapon", "sword", "firearm"),
    "complex_electronics": (
        "camera", "smartphone", "computer", "keyboard", "power bank",
        "battery system", "robot", "PCB", "drone", "smart electronic device",
        "complex circuit", "multi-sensor", "AI hardware", "AI tracking",
        "precision electronics", "dock", "docking station", "SSD",
        "storage drive", "charger", "charging hub", "battery hub",
        "computer hardware", "Thunderbolt", "USB high-speed controller",
        "20Gbps", "SSD storage", "battery management",
        "fast charging electronics", "battery health check",
    ),
    "wireless": (
        "Bluetooth", "Wi-Fi", "WiFi", "2.4G", "cellular",
        "radio transmission", "wireless",
    ),
    "high_regulation": (
        "food", "supplement", "oral", "cosmetic", "cream", "serum",
        "medical", "medicine", "treatment", "therapeutic", "drug",
    ),
    "large_or_heavy": (
        "large furniture", "full-size furniture", "treadmill",
        "large fitness equipment", "heavy machinery", "large appliance",
        "industrial machine",
    ),
    "high_engineering_barrier": (
        "complex mechanical engineering", "precision optics",
        "high precision electronics", "custom complex mold",
        "complex proprietary tooling", "hardware-software co-design",
        "complex software and hardware", "robotics platform",
    ),
}

POSITIVE_SIGNAL_PATTERNS: dict[str, tuple[str, ...]] = {
    "simple_structure": (r"\bsimple\b", r"\bsimple structure\b", r"\bbasic construction\b"),
    "non_electronic": (
        r"\bnon[- ]electronic\b", r"\bnon[- ]electric\b", r"\bno electricity\b",
    ),
    "small_or_compact": (
        r"\bsmall\b", r"\bcompact\b", r"\bmini\b", r"\bportable\b",
        r"\b(?:[1-9]|1\d|20)[ -]?L\b",
    ),
    "lightweight": (r"\blightweight\b", r"\bultra[- ]light\b"),
    "common_material": (
        r"\bpolyester\b", r"\bnylon\b", r"\brecycled nylon\b",
        r"\bABS\b", r"\bPP\b", r"\bsilicone\b", r"\bPU leather\b",
        r"\bleather\b", r"\bsimple steel\b", r"\baluminum\b",
        r"\bfabric\b", r"\bpaper\b", r"\bwood\b",
    ),
    "simple_sewn_product": (
        r"\bpouch\b", r"\btravel pouch\b", r"\bbag\b", r"\bbackpack\b",
        r"\bsimple wallet\b",
    ),
    "simple_plastic_product": (r"\bABS\b", r"\bPP\b", r"\bplastic\b", r"\bsilicone\b"),
    "simple_metal_product": (r"\baluminum\b", r"\bsimple steel\b", r"\bsheet metal\b"),
    "simple_assembly": (r"\bsimple assembly\b", r"\beasy to assemble\b"),
    "common_consumer_category": (
        r"\borganizer\b", r"\borganiser\b", r"\bkey organizer\b",
        r"\bkey organiser\b", r"\bcable organizer\b", r"\bpouch\b",
        r"\bbag\b", r"\bbackpack\b", r"\bsimple wallet\b",
        r"\bholder\b", r"\bstand\b", r"\bsimple rack\b",
        r"\bsimple clip\b", r"\bsimple hook\b", r"\bstationery accessory\b",
        r"\bdesk accessory\b", r"\bsimple storage product\b",
        r"\bpet accessory\b", r"\bsimple home accessory\b",
        r"\bsimple cleaning accessory\b",
        r"\bsimple non[- ]electric kitchen accessory\b",
        r"\bcraft accessory\b", r"\bhobby accessory\b",
    ),
    "easy_shipping": (r"\beasy shipping\b", r"\beasy to ship\b", r"\bflat pack\b"),
    "low_breakage_risk": (r"\bshatterproof\b", r"\bunbreakable\b", r"\blow breakage risk\b"),
}

REVIEW_COMPLEXITY_PATTERNS = (
    r"\btitanium\b", r"\bcarbon fiber\b", r"\bprecision CNC\b",
    r"\baerospace grade\b", r"\bhigh precision machining\b",
    r"\bpatented material\b", r"\bspecial mechanism\b",
    r"\bmultifunction(?:al)?\b", r"\b\d+[- ](?:in[- ]1|features?)\b",
    r"\bmodular paintbox\b", r"\bpassive cool(?:er|ing)\b",
)


@dataclass(frozen=True)
class FeasibilityResult:
    """Suitability for the next supplier and micro-innovation research layer."""

    feasibility_status: FeasibilityStatus
    feasibility_score: int
    feasibility_reason: str
    risk_flags: list[str]
    positive_signals: list[str]


def filter_feasibility(product: Product) -> FeasibilityResult:
    """Calibrate feasibility without claiming supplier or production proof."""
    text = " ".join((product.title, product.description, product.category))
    risk_flags = [
        risk for risk, patterns in RISK_PATTERNS.items() if _matched(text, patterns)
    ]
    if "wireless" in risk_flags:
        risk_flags.append("high_certification_risk")

    positive_signals = [
        signal
        for signal, patterns in POSITIVE_SIGNAL_PATTERNS.items()
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
    ]

    if risk_flags:
        return FeasibilityResult(
            "REJECT",
            max(0, 28 - 6 * len(risk_flags)),
            "rejected risks: " + ", ".join(risk_flags),
            risk_flags,
            positive_signals,
        )

    review_complexity = any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in REVIEW_COMPLEXITY_PATTERNS
    )
    score = min(100, 35 + 8 * len(positive_signals))
    simple_consumer = "common_consumer_category" in positive_signals

    if simple_consumer and len(positive_signals) >= 4 and not review_complexity:
        return FeasibilityResult(
            "PASS",
            max(70, score),
            (
                "simple consumer product; " + ", ".join(positive_signals)
                + "; suitable for supplier and micro-innovation research; "
                "supplier, cost, and IP not yet verified"
            ),
            [],
            positive_signals,
        )

    if review_complexity:
        score = min(69, max(45, score))
        reason = (
            "special material, mechanism, or processing complexity requires review; "
            "supplier, cost, and IP not yet verified"
        )
    elif positive_signals:
        score = min(69, score)
        reason = (
            "positive signals: " + ", ".join(positive_signals)
            + "; product simplicity or manufacturing detail remains uncertain"
        )
    else:
        reason = "insufficient information for personal seller feasibility"

    return FeasibilityResult("REVIEW", score, reason, [], positive_signals)


def _matched(text: str, patterns: tuple[str, ...]) -> bool:
    return any(
        re.search(
            rf"\b{re.escape(pattern)}{'s?' if not pattern.endswith('s') else ''}\b",
            text,
            re.IGNORECASE,
        )
        for pattern in patterns
    )
