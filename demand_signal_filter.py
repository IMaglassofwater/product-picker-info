"""Source-aware record routing and deterministic demand-signal scoring."""

from dataclasses import dataclass
import re
from typing import Literal

from models import Product


RecordRole = Literal["product", "demand_signal", "software", "inspiration", "uncertain"]
SignalStatus = Literal["HIGH", "MEDIUM", "LOW", "NOT_DEMAND"]
SignalType = Literal[
    "purchase_intent",
    "product_gap",
    "price_pain",
    "feature_request",
    "usage_problem",
    "recommendation_request",
    "DIY_workaround",
    "general_discussion",
]


@dataclass(frozen=True)
class RecordRoleResult:
    """Explain what kind of source record a Product instance represents."""

    record_role: RecordRole
    reason: str


@dataclass(frozen=True)
class DemandSignalResult:
    """Explain the strength and primary type of a user demand signal."""

    signal_status: SignalStatus
    signal_score: int
    signal_type: SignalType
    reason: str


SIGNAL_RULES: dict[SignalType, tuple[tuple[str, int], ...]] = {
    "purchase_intent": (
        (r"\blooking for\b", 45),
        (r"\blooking to buy\b", 50),
        (r"\bi (?:want|need) (?:a|an|something)\b", 35),
    ),
    "product_gap": (
        (r"\bcan(?:not|'t) find\b", 45),
        (r"\bdoes anyone make\b", 45),
        (r"\bis there (?:a|an)\b", 30),
        (r"\b(?:works?|needs? to work) with\b", 25),
    ),
    "price_pain": (
        (r"\btoo expensive\b", 50),
        (r"\bcheaper\b", 30),
        (r"\bcan(?:not|'t) afford\b", 50),
    ),
    "feature_request": (
        (r"\bholds? up to\b", 25),
        (r"\b(?:ideally|must|should|needs? to)\b", 20),
        (r"\bi want something that\b", 40),
        (r"\bproblem with\b", 30),
    ),
    "usage_problem": (
        (r"\bdoesn(?:'t| not) work\b", 40),
        (r"\bissue with\b", 35),
        (r"\bstruggle with\b", 35),
    ),
    "recommendation_request": (
        (r"\bsuggestions?\b", 40),
        (r"\brecommend(?:ation|ations|ed)?\b", 40),
        (r"\bwhat should i get\b", 45),
        (r"\banyone know\b", 35),
        (r"\bconsidering adding\b", 35),
    ),
    "DIY_workaround": (
        (r"\bmade (?:one|it) (?:myself|personally)\b", 50),
        (r"\bmade it myself\b", 50),
        (r"\bDIY\b", 25),
        (r"\bmy own solution\b", 40),
    ),
}

ROLE_DEMAND_PATTERNS = tuple(
    pattern for rules in SIGNAL_RULES.values() for pattern, _score in rules
) + (
    r"\bwish\b",
    r"\balternative\b",
)


def classify_record_role(
    product: Product,
    opportunity_type: str = "uncertain",
) -> RecordRoleResult:
    """Route a source record without treating every Reddit post as a product."""
    source = product.source_platform.lower()
    text = f"{product.title} {product.description}"

    if source == "kickstarter":
        return RecordRoleResult("product", "Kickstarter project record")

    if source == "product_hunt":
        role: RecordRole = (
            opportunity_type
            if opportunity_type in {"software", "inspiration"}
            else "product" if opportunity_type == "physical" else "uncertain"
        )
        return RecordRoleResult(role, f"Product Hunt {opportunity_type} routing")

    if source in {"reddit", "reddit_arctic_shift"}:
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in ROLE_DEMAND_PATTERNS):
            return RecordRoleResult(
                "demand_signal", "Reddit post expresses a need, gap, or request"
            )
        if opportunity_type == "physical":
            return RecordRoleResult(
                "product", "Reddit post describes or displays a concrete product"
            )
        if re.search(
            r"\b(?:backpack|organizer|organiser|pouch|bag|stand|holder|accessory)\b",
            text,
            re.IGNORECASE,
        ):
            return RecordRoleResult(
                "product", "Reddit post describes a concrete consumer product"
            )
        return RecordRoleResult("uncertain", "Reddit post role is not explicit")

    if opportunity_type in {"physical", "software", "inspiration"}:
        role = "product" if opportunity_type == "physical" else opportunity_type
        return RecordRoleResult(role, f"role derived from {opportunity_type}")
    return RecordRoleResult("uncertain", "insufficient evidence for record role")


def filter_demand_signal(product: Product) -> DemandSignalResult:
    """Score explicit user needs without inventing a product solution."""
    text = f"{product.title} {product.description}"
    scores: dict[SignalType, int] = {}
    evidence: dict[SignalType, list[str]] = {}
    for signal_type, rules in SIGNAL_RULES.items():
        matches = [pattern for pattern, _score in rules if re.search(pattern, text, re.I)]
        if matches:
            scores[signal_type] = min(
                100,
                sum(score for pattern, score in rules if pattern in matches),
            )
            evidence[signal_type] = matches

    if not scores:
        return DemandSignalResult(
            "NOT_DEMAND", 0, "general_discussion", "no explicit demand signal"
        )

    total_score = min(100, max(scores.values()) + 15 * (len(scores) - 1))
    priority = (
        "price_pain", "DIY_workaround", "product_gap", "purchase_intent",
        "recommendation_request", "feature_request", "usage_problem",
    )
    primary = max(priority, key=lambda kind: (scores.get(kind, -1), -priority.index(kind)))
    status: SignalStatus = "HIGH" if total_score >= 60 else "MEDIUM" if total_score >= 35 else "LOW"
    found_types = [kind for kind in priority if kind in scores]
    return DemandSignalResult(
        signal_status=status,
        signal_score=total_score,
        signal_type=primary,
        reason="demand signals: " + ", ".join(found_types),
    )
