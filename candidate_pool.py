"""Unified rule-based micro-innovation candidate analysis layer."""

from dataclasses import dataclass
import hashlib
from typing import Literal

from creative_content_filter import CreativeContentResult
from models import Product


CandidateType = Literal[
    "validated_product", "demand_opportunity", "inspiration_product",
    "consumer_trend",
]


@dataclass(frozen=True)
class MicroInnovationCandidate:
    """A qualified opportunity normalized for downstream research."""

    candidate_id: str
    candidate_type: CandidateType
    source_platform: str
    source_url: str
    title: str
    summary: str
    candidate_score: int
    feasibility_score: int
    demand_score: int
    market_validation_score: int
    micro_innovation_score: int
    reason: str
    signals: list[str]
    raw_reference_id: str


DEMAND_MICRO_WEIGHTS = {
    "existing_simple_product": 10,
    "clear_feature_gap": 12,
    "clear_size_requirement": 8,
    "clear_usage_scenario": 6,
    "clear_price_pain": 8,
    "appearance_positioning_gap": 10,
    "accessibility_problem": 10,
    "storage_or_organization": 5,
    "portability_problem": 5,
    "DIY_workaround": 12,
    "simple_material_change": 5,
    "low_tech_modification": 12,
}

VALIDATED_MICRO_WEIGHTS = {
    "simple_structure": 15,
    "non_electronic": 12,
    "small_or_compact": 8,
    "lightweight": 6,
    "common_material": 8,
    "simple_sewn_product": 10,
    "simple_plastic_product": 10,
    "simple_metal_product": 8,
    "simple_assembly": 12,
    "common_consumer_category": 12,
    "easy_shipping": 8,
    "low_breakage_risk": 6,
}


def build_consumer_trend_candidate(
    product: Product,
    *,
    status: str,
    feasibility_score: int,
    market_signal_score: int,
    micro_innovation_score: int,
    signals: list[str],
    reason: str,
    commodity_status: str,
) -> MicroInnovationCandidate | None:
    """Build a candidate from a simple Amazon trend item, without sales claims."""
    if status != "candidate" or commodity_status != "PROMISING":
        return None
    candidate_score = round(
        0.40 * feasibility_score
        + 0.35 * market_signal_score
        + 0.25 * micro_innovation_score
    )
    return _candidate(
        product,
        "consumer_trend",
        candidate_score,
        max(0, min(100, feasibility_score)),
        0,
        max(0, min(100, market_signal_score)),
        max(0, min(100, micro_innovation_score)),
        reason,
        list(dict.fromkeys(signals)),
    )


def build_inspiration_candidate(
    product: Product,
    result: CreativeContentResult,
) -> MicroInnovationCandidate | None:
    """Build an inspiration candidate from eligible creative product content."""
    if not result.eligible:
        return None
    candidate_score = round(
        0.45 * result.feasibility_score
        + 0.40 * result.micro_innovation_score
        + 0.15 * result.information_clarity_score
    )
    return _candidate(
        product,
        "inspiration_product",
        candidate_score,
        result.feasibility_score,
        0,
        0,
        result.micro_innovation_score,
        result.reason,
        result.signals,
    )


def build_demand_candidate(
    product: Product,
    *,
    demand_opportunity_status: str,
    demand_opportunity_score: int,
    signal_score: int,
    signal_type: str,
    opportunity_flags: list[str],
) -> MicroInnovationCandidate | None:
    """Build a candidate only from a PRODUCTIZABLE demand opportunity."""
    if demand_opportunity_status != "PRODUCTIZABLE":
        return None
    signals = list(dict.fromkeys(opportunity_flags))
    clarity_flags = {
        "clear_feature_gap", "clear_size_requirement", "clear_usage_scenario",
        "clear_price_pain",
    }
    demand_score = min(
        100,
        max(0, signal_score)
        + 4 * len(clarity_flags.intersection(signals))
        + (5 if signal_type == "purchase_intent" else 0),
    )
    micro_score = min(
        100,
        26 + sum(DEMAND_MICRO_WEIGHTS.get(signal, 0) for signal in signals),
    )
    feasibility_score = max(0, min(100, demand_opportunity_score))
    candidate_score = round(
        0.35 * demand_score + 0.35 * feasibility_score + 0.30 * micro_score
    )
    return _candidate(
        product,
        "demand_opportunity",
        candidate_score,
        feasibility_score,
        demand_score,
        0,
        micro_score,
        (
            "productizable demand with explicit low-tech micro-innovation signals; "
            "supplier and cost research still required"
        ),
        signals,
    )


def build_validated_product_candidate(
    product: Product,
    *,
    feasibility_status: str,
    feasibility_score: int,
    positive_signals: list[str],
) -> MicroInnovationCandidate | None:
    """Build a candidate only from a product that passed feasibility rules."""
    if feasibility_status != "PASS":
        return None
    signals = list(dict.fromkeys(positive_signals))
    market_score = _market_validation_score(product.raw_data)
    micro_score = min(
        100,
        20 + sum(VALIDATED_MICRO_WEIGHTS.get(signal, 0) for signal in signals),
    )
    bounded_feasibility = max(0, min(100, feasibility_score))
    candidate_score = round(
        0.40 * bounded_feasibility
        + 0.35 * market_score
        + 0.25 * micro_score
    )
    return _candidate(
        product,
        "validated_product",
        candidate_score,
        bounded_feasibility,
        0,
        market_score,
        micro_score,
        (
            "feasibility-passed product with smoothly scored market validation; "
            "supplier and micro-innovation research still required"
        ),
        signals,
    )


def deduplicate_candidates(
    candidates: list[MicroInnovationCandidate],
) -> list[MicroInnovationCandidate]:
    """Keep the highest-scoring candidate for each source URL."""
    by_url: dict[str, MicroInnovationCandidate] = {}
    for candidate in candidates:
        current = by_url.get(candidate.source_url)
        if current is None or candidate.candidate_score > current.candidate_score:
            by_url[candidate.source_url] = candidate
    return list(by_url.values())


def _market_validation_score(raw_data: dict) -> int:
    backers = _number(raw_data.get("backers_count", raw_data.get("backers")))
    funded = _number(
        raw_data.get("percent_funded", raw_data.get("funding_percentage"))
    )
    if backers is None:
        backer_score = 0
    elif backers < 100:
        backer_score = 30
    elif backers < 500:
        backer_score = 55
    elif backers < 2000:
        backer_score = 75
    else:
        backer_score = 90

    if funded is None:
        funding_score = 0
    elif funded < 100:
        funding_score = max(0, round(funded * 0.3))
    elif funded < 300:
        funding_score = 45 + round((funded - 100) * 0.075)
    elif funded < 1000:
        funding_score = 60 + round((funded - 300) * 0.02)
    else:
        funding_score = min(85, 74 + round((funded - 1000) / 1000))
    if backers is None:
        return funding_score
    if funded is None:
        return backer_score
    return round(0.75 * backer_score + 0.25 * funding_score)


def _candidate(
    product: Product,
    candidate_type: CandidateType,
    candidate_score: int,
    feasibility_score: int,
    demand_score: int,
    market_validation_score: int,
    micro_innovation_score: int,
    reason: str,
    signals: list[str],
) -> MicroInnovationCandidate:
    identity = f"{candidate_type}|{product.url}".encode("utf-8")
    candidate_id = hashlib.sha256(identity).hexdigest()[:24]
    return MicroInnovationCandidate(
        candidate_id=candidate_id,
        candidate_type=candidate_type,
        source_platform=product.source_platform,
        source_url=product.url,
        title=product.title,
        summary=product.description,
        candidate_score=max(0, min(100, candidate_score)),
        feasibility_score=feasibility_score,
        demand_score=demand_score,
        market_validation_score=market_validation_score,
        micro_innovation_score=micro_innovation_score,
        reason=reason,
        signals=signals,
        raw_reference_id=product.project_id,
    )


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None
