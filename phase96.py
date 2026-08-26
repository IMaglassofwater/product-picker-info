"""Offline Phase 9.6 candidate rebuild, Gemini coverage, and report helpers."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

import db
from ai_filter import run_triage_batch
from ai_providers import BaseAIProvider
from candidate_pool import (
    MicroInnovationCandidate,
    build_consumer_trend_candidate,
    build_demand_candidate,
    build_inspiration_candidate,
    build_validated_product_candidate,
    deduplicate_candidates,
)
from commodity_filter import filter_commodity
from creative_content_filter import filter_creative_content
from daily_ranker import OpportunityInput, to_triage_candidate
from demand_opportunity_filter import filter_demand_opportunity
from demand_signal_filter import classify_record_role, filter_demand_signal
from feasibility_filter import filter_feasibility
from models import Product
from opportunity_specificity import assess_specificity
from rule_filter import filter_product
from scrapers.amazon_trends import filter_amazon_trend


GEMINI_MODEL = "gemini-3.5-flash-lite"
SOURCE_ORDER = (
    "reddit_arctic_shift", "amazon", "kickstarter", "indiegogo",
    "yanko_design", "product_hunt",
)


@dataclass
class CoverageRunResult:
    selected: int = 0
    successful: int = 0
    failed: int = 0
    skipped_existing: int = 0
    stopped_by_blocker: bool = False
    statuses: Counter = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)


def rebuild_candidate_pool(products: list[Product] | None = None) -> list[MicroInnovationCandidate]:
    """Reapply the finalized offline gates to stored products, without network access."""
    products = products if products is not None else db.get_all_products()
    built: list[MicroInnovationCandidate] = []
    for product in products:
        rule = filter_product(product)
        role = classify_record_role(product, rule.opportunity_type)
        if role.record_role == "product":
            feasibility = filter_feasibility(product)
            candidate = build_validated_product_candidate(
                product,
                feasibility_status=feasibility.feasibility_status,
                feasibility_score=feasibility.feasibility_score,
                positive_signals=feasibility.positive_signals,
            )
            if candidate:
                built.append(candidate)
        elif role.record_role == "demand_signal":
            demand = filter_demand_signal(product)
            if demand.signal_status in {"HIGH", "MEDIUM"}:
                opportunity = filter_demand_opportunity(product, demand)
                candidate = build_demand_candidate(
                    product,
                    demand_opportunity_status=opportunity.demand_opportunity_status,
                    demand_opportunity_score=opportunity.demand_opportunity_score,
                    signal_score=demand.signal_score,
                    signal_type=demand.signal_type,
                    opportunity_flags=opportunity.opportunity_flags,
                )
                if candidate:
                    built.append(candidate)
        if product.source_platform == "yanko_design":
            candidate = build_inspiration_candidate(product, filter_creative_content(product))
            if candidate:
                built.append(candidate)
        if product.source_platform == "amazon":
            trend = filter_amazon_trend(product)
            commodity = filter_commodity(product)
            candidate = build_consumer_trend_candidate(
                product, status=trend.status,
                feasibility_score=trend.feasibility_score,
                market_signal_score=trend.market_signal_score,
                micro_innovation_score=trend.micro_innovation_score,
                signals=trend.signals, reason=trend.reason,
                commodity_status=commodity.commodity_status,
            )
            if candidate:
                built.append(candidate)
    candidates = deduplicate_candidates(built)
    db.save_candidates(candidates)
    for candidate in candidates:
        result = assess_specificity(
            candidate.title, candidate.summary, candidate.signals,
            candidate.candidate_type, candidate.source_platform,
        )
        db.save_specificity_result(candidate.candidate_id, result, rule_version="v1")
    return db.get_all_candidates()


def missing_coverage(candidates: list[OpportunityInput], provider: str = "gemini", model: str = GEMINI_MODEL) -> list[OpportunityInput]:
    return [
        candidate for candidate in candidates
        if not db.has_triage_result(candidate.candidate_id, provider, model)
    ]


def run_coverage(
    candidates: list[OpportunityInput], *, provider: BaseAIProvider,
    products: dict[str, Product] | None = None, batch_size: int = 10,
    consecutive_failure_limit: int = 3,
    has_result: Callable[[str, str, str], bool] = db.has_triage_result,
    save_result: Callable = db.save_triage_result,
) -> CoverageRunResult:
    """Triage missing candidates sequentially in bounded batches and stop after 3 failures."""
    batch_size = max(1, min(10, batch_size))
    result = CoverageRunResult()
    consecutive_failures = 0
    products = products or {}
    commodity = db.get_candidate_commodity()
    ordered = sorted(candidates, key=lambda item: (-item.candidate_score, item.source_platform, item.candidate_id))
    for offset in range(0, len(ordered), batch_size):
        for candidate in ordered[offset:offset + batch_size]:
            if has_result(candidate.candidate_id, provider.provider_name, provider.model_name):
                result.skipped_existing += 1
                continue
            result.selected += 1
            adapted = to_triage_candidate(candidate)
            batch = run_triage_batch(
                [adapted], products=products, commodity=commodity,
                provider=provider, has_result=has_result, save_result=save_result,
                force_reanalyze=False,
            )
            if batch.processed:
                triage = batch.processed[0]
                result.successful += 1
                result.statuses[triage.triage_status] += 1
                consecutive_failures = 0
            else:
                result.failed += 1
                result.errors.append(f"{candidate.candidate_id}: AI triage failed")
                consecutive_failures += 1
                if consecutive_failures >= consecutive_failure_limit:
                    result.stopped_by_blocker = True
                    return result
    return result
