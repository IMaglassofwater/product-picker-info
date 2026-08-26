"""Deterministic dual-track opportunity classification and filtering."""

from dataclasses import dataclass
import re
from typing import Literal

from models import Product


OpportunityType = Literal["physical", "software", "inspiration", "uncertain"]
FilterStatus = Literal["candidate", "rejected", "uncertain"]

PHYSICAL_SIGNALS = (
    "organizer", "holder", "case", "clip", "mount", "stand", "bag",
    "pouch", "rack", "hook", "bottle", "container", "EDC", "tool",
    "camping gear", "travel accessory", "desk accessory",
    "storage accessory", "physical tool", "DIY accessory",
)

PHYSICAL_PRIORITY_SIGNALS = (
    "small", "compact", "lightweight", "simple", "portable", "low cost",
    "easy to carry", "EDC", "travel", "camping", "desk", "organizer",
    "storage", "simple tool", "DIY accessory",
)

PHYSICAL_RISK_SIGNALS = (
    "food", "supplement", "medicine", "medical", "cosmetic", "cream",
    "serum", "drug", "bluetooth", "wireless", "router",
    "complex electronics", "certification required",
)

SOFTWARE_SIGNALS = (
    "browser", "dashboard", "AI agent", "Git", "API", "SaaS",
    "analytics", "extension", "automation", "editor", "workspace",
    "web app", "software", "app", "plugin", "UI", "design system",
    "productivity tool", "ElevenLabs",
)

SOFTWARE_MVP_SIGNALS = (
    "web tool", "app", "Chrome extension", "browser extension",
    "productivity tool", "marketing tool", "content tool", "AI wrapper",
    "automation", "analytics", "dashboard", "plugin", "no-code",
    "AI agent", "AI agents", "editor", "UI",
)

SOFTWARE_COMPLEX_SIGNALS = (
    "enterprise SaaS", "enterprise platform", "AI infrastructure",
    "model training", "database infrastructure",
    "cybersecurity infrastructure", "financial infrastructure",
    "banking platform", "developer infrastructure", "distributed system",
    "large engineering team",
)

INSPIRATION_SIGNALS = (
    "concept design", "design concept", "concept product",
    "industrial design", "experimental design",
)


@dataclass(frozen=True)
class FilterResult:
    """Explainable result from free opportunity classification rules."""

    filter_score: int
    status: FilterStatus
    reason: str
    opportunity_type: OpportunityType


def filter_product(product: Product) -> FilterResult:
    """Classify and score a Product without modifying the source object."""
    structured_context = _structured_context(product)
    text = " ".join(
        (product.title, product.description, product.category, structured_context)
    )
    physical_matches = _matched_keywords(text, PHYSICAL_SIGNALS)
    software_matches = _matched_keywords(text, SOFTWARE_SIGNALS)
    inspiration_matches = _matched_keywords(text, INSPIRATION_SIGNALS)
    risk_matches = _matched_keywords(text, PHYSICAL_RISK_SIGNALS)

    opportunity_type = _classify_opportunity(
        product, physical_matches, software_matches, inspiration_matches,
        risk_matches,
    )

    if opportunity_type == "physical":
        result = _filter_physical(text, physical_matches)
    elif opportunity_type == "software":
        result = _filter_software(text, software_matches)
    elif opportunity_type == "inspiration":
        result = FilterResult(
            filter_score=50,
            status="candidate",
            reason="inspiration signals: " + ", ".join(inspiration_matches),
            opportunity_type="inspiration",
        )
    else:
        result = FilterResult(
            filter_score=40,
            status="uncertain",
            reason=(
                "insufficient signals to classify as physical, software, "
                "or inspiration"
            ),
            opportunity_type="uncertain",
        )
    return _with_source_signals(product, result)


def _classify_opportunity(
    product: Product,
    physical_matches: list[str],
    software_matches: list[str],
    inspiration_matches: list[str],
    risk_matches: list[str],
) -> OpportunityType:
    source = product.source_platform.lower()
    if inspiration_matches and source in {"yanko_design", "designboom"}:
        return "inspiration"
    if software_matches and len(physical_matches) < 2:
        return "software"
    if len(physical_matches) >= 2 or (risk_matches and not software_matches):
        return "physical"
    if len(inspiration_matches) >= 2:
        return "inspiration"
    if software_matches:
        return "software"
    return "uncertain"


def _filter_physical(text: str, identity_matches: list[str]) -> FilterResult:
    priority_matches = _matched_keywords(text, PHYSICAL_PRIORITY_SIGNALS)
    risk_matches = _matched_keywords(text, PHYSICAL_RISK_SIGNALS)
    score = _bounded_score(50 + 8 * len(priority_matches) - 30 * len(risk_matches))
    status: FilterStatus = "rejected" if risk_matches or score < 50 else "candidate"
    reason = _reason("physical", identity_matches, priority_matches, risk_matches)
    return FilterResult(score, status, reason, "physical")


def _filter_software(text: str, identity_matches: list[str]) -> FilterResult:
    mvp_matches = _matched_keywords(text, SOFTWARE_MVP_SIGNALS)
    complex_matches = _matched_keywords(text, SOFTWARE_COMPLEX_SIGNALS)
    score = _bounded_score(55 + 8 * len(mvp_matches) - 30 * len(complex_matches))
    status: FilterStatus = "candidate" if score >= 50 else "rejected"
    reason = _reason("software", identity_matches, mvp_matches, complex_matches)
    return FilterResult(score, status, reason, "software")


def _reason(
    opportunity_type: str,
    identity_matches: list[str],
    positive_matches: list[str],
    negative_matches: list[str],
) -> str:
    parts = [f"type: {opportunity_type}"]
    if identity_matches:
        parts.append("signals: " + ", ".join(identity_matches))
    if positive_matches:
        parts.append("priority: " + ", ".join(positive_matches))
    if negative_matches:
        parts.append("risk: " + ", ".join(negative_matches))
    return "; ".join(parts)


def _bounded_score(score: int) -> int:
    return max(0, min(100, score))


def _matched_keywords(text: str, keywords: tuple[str, ...]) -> list[str]:
    """Return signals found as case-insensitive whole phrases."""
    return [
        keyword
        for keyword in keywords
        if re.search(
            rf"\b{re.escape(keyword)}{'s?' if not keyword.endswith('s') else ''}\b",
            text,
            re.IGNORECASE,
        )
    ]


def _structured_context(product: Product) -> str:
    """Flatten trusted public metadata fields for deterministic matching."""
    values: list[str] = []
    raw_data = product.raw_data
    tagline = raw_data.get("tagline")
    if isinstance(tagline, str):
        values.append(tagline)
    topics = raw_data.get("topics")
    if isinstance(topics, list):
        values.extend(item for item in topics if isinstance(item, str))
    values.extend(_metadata_strings(raw_data.get("metadata")))
    return " ".join(values)


def _metadata_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_metadata_strings(item))
        return result
    if isinstance(value, dict):
        result = []
        for item in value.values():
            result.extend(_metadata_strings(item))
        return result
    return []


def _with_source_signals(product: Product, result: FilterResult) -> FilterResult:
    """Append simple source-specific evidence without changing classification."""
    reasons: list[str] = []
    if product.source_platform == "kickstarter":
        percent_funded = _numeric(product.raw_data.get("percent_funded"))
        if percent_funded is not None and percent_funded >= 100:
            reasons.append("market validated: funded >= 100%")
    elif product.source_platform == "reddit_arctic_shift":
        score = _numeric(product.raw_data.get("score"))
        comments = _numeric(product.raw_data.get("num_comments"))
        if score is not None or comments is not None:
            reasons.append(
                "historical engagement: "
                f"score={_format_metric(score)}, "
                f"comments={_format_metric(comments)}"
            )
    if not reasons:
        return result
    return FilterResult(
        filter_score=result.filter_score,
        status=result.status,
        reason=result.reason + "; " + "; ".join(reasons),
        opportunity_type=result.opportunity_type,
    )


def _numeric(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_metric(value: float | None) -> str:
    if value is None:
        return "unknown"
    return str(int(value)) if value.is_integer() else str(value)
