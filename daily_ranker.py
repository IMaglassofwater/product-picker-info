"""Transparent offline ranking for the daily opportunity shortlist."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
import sqlite3
from typing import Literal

import db
from deep_analysis import DeepAnalysisResult
from final_deep_gate import FinalDeepGateResult, evaluate_final_deep_gate
from models import AITriageResult
from software_analysis import SoftwareAnalysisResult, stable_candidate_id
from candidate_pool import MicroInnovationCandidate
from opportunity_specificity import SpecificityResult, assess_specificity


OpportunityType = Literal["Physical", "Software"]
MAX_DAILY = 10
MAX_SOFTWARE = 2
MAX_PER_THEME = 3
MIN_FINAL_SCORE = 55
HARD_RISKS = {
    "weapon", "weapon_or_blade", "regulated", "high_regulation",
    "complex_electronics", "wireless", "large_or_heavy", "bulky_shipping",
}


@dataclass(frozen=True)
class RankComponents:
    ai_quality: int
    evidence: int
    feasibility: int
    actionability: int
    cross_source: int
    freshness: int

    @property
    def total(self) -> int:
        return sum((self.ai_quality, self.evidence, self.feasibility,
                    self.actionability, self.cross_source, self.freshness))


@dataclass
class OpportunityInput:
    candidate_id: str
    title: str
    summary: str
    opportunity_type: OpportunityType
    candidate_type: str
    source_platform: str
    source_url: str
    candidate_score: int
    feasibility_score: int = 0
    demand_score: int = 0
    market_validation_score: int = 0
    micro_innovation_score: int = 0
    signals: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    positive_signals: list[str] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)
    created_at: str = ""
    triage: AITriageResult | None = None
    physical_analysis: DeepAnalysisResult | None = None
    software_analysis: SoftwareAnalysisResult | None = None
    theme: str = "other"
    opportunity_group: str | None = None

    @property
    def display_title(self) -> str:
        return make_display_title(self.title, self.summary)


@dataclass
class RankedOpportunity:
    candidate: OpportunityInput
    final_rank_score: int
    components: RankComponents
    analysis_source: str
    needs_analysis: bool
    selection_reason: str = ""
    exclusion_reason: str = ""
    rank: int | None = None
    specificity: SpecificityResult | None = None
    final_deep_gate: FinalDeepGateResult | None = None


@dataclass
class DailyRankingResult:
    eligible_candidates: int
    rejected_by_quality_gate: int
    physical_eligible: int
    software_eligible: int
    near_duplicates_removed: int
    theme_quota_removed: int
    software_quota_removed: int
    final: list[RankedOpportunity]
    next_ten: list[RankedOpportunity]
    eligible_before_specificity: int = 0
    removed_too_broad: int = 0
    held_for_review: int = 0
    specificity_counts: dict[str, int] = field(default_factory=dict)
    removed_or_held: list[RankedOpportunity] = field(default_factory=list)
    deep_gate_counts: dict[str, int] = field(default_factory=dict)
    deep_gate_held_or_removed: list[RankedOpportunity] = field(default_factory=list)


def infer_theme(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".casefold()
    if "backpacking pillow" in text or "camping pillow" in text:
        return "outdoor_accessories"
    rules = (
        ("bags_and_carry", ("backpack", "fanny pack", "sling", "pouch", "carry bag")),
        ("storage_and_organization", ("organizer", "organiser", "storage", "holder")),
        ("travel_accessories", ("travel", "luggage", "packing", "one-bag", "onebag")),
        ("desk_and_office", ("desk", "office", "workspace", "productivity")),
        ("outdoor_accessories", ("camping", "outdoor", "hiking")),
        ("home_and_living", ("home", "kitchen", "can opener", "lamp")),
        ("pet_accessories", ("pet", "dog", "cat")),
        ("tools_and_edc", ("edc", "tool", "key organizer", "key organiser")),
    )
    return next((theme for theme, words in rules if any(word in text for word in words)), "other")


def make_display_title(title: str, summary: str) -> str:
    """Return a readable display-only fallback without changing the source title."""
    original = " ".join(title.split())
    if len(original) >= 4 and original.casefold() not in {"my", "help", "question"}:
        return original
    cleaned = " ".join(re.sub(r"<[^>]+>", " ", summary).split())
    if "paperrepublic" in cleaned.casefold() and "leather" in cleaned.casefold():
        return "PaperRepublic alternative / DIY leather journal"
    fragment = re.split(r"(?<=[.!?])\s+|\n", cleaned, maxsplit=1)[0].strip()
    return (fragment or original or "Untitled opportunity")[:60].rstrip()


def infer_opportunity_group(title: str, summary: str = "") -> str | None:
    text = f"{title} {summary}".casefold()
    title_text = title.casefold()
    if "app" in title_text and "fabric" in text:
        return "fabric_travel_app"
    groups = (
        ("backpacking_pillow", ("backpacking pillow", "camping pillow")),
        ("work_backpack", ("work backpack", "office backpack")),
        ("key_organizer", ("key organizer", "key organiser", "key holder")),
        ("manual_can_opener", ("manual can opener",)),
        ("fanny_pack", ("fanny pack", "waist pack")),
        ("desk_lamp", ("desk lamp",)),
    )
    return next((group for group, words in groups if any(word in text for word in words)), None)


def _analysis_quality(candidate: OpportunityInput) -> tuple[int, str, bool]:
    if candidate.opportunity_type == "Software" and candidate.software_analysis:
        return candidate.software_analysis.software_score * 3, "Software Analysis", False
    if candidate.opportunity_type == "Physical" and candidate.physical_analysis:
        decision = evaluate_final_deep_gate(candidate.physical_analysis)
        if decision.status != "HUMAN_REVIEW":
            return candidate.physical_analysis.deep_score * 3, "Physical Deep Analysis", False
    if candidate.triage:
        return candidate.triage.triage_score * 3, "Cheap Triage Fallback", True
    return round(candidate.candidate_score * 0.3), "Candidate Score Fallback", True


def _evidence_score(candidate: OpportunityInput) -> int:
    source = candidate.source_platform.casefold()
    if "reddit" in source:
        return 18 if candidate.demand_score >= 80 else 13 if candidate.demand_score >= 60 else 7
    if "kickstarter" in source:
        return 19 if candidate.market_validation_score >= 80 else 14 if candidate.market_validation_score >= 50 else 8
    if "amazon" in source:
        reviews = candidate.raw_data.get("review_count") or 0
        rank = candidate.raw_data.get("rank")
        return 17 if reviews or rank else 10
    if "yanko" in source:
        return 6
    if "product_hunt" in source:
        return 7
    base = max(candidate.demand_score, candidate.market_validation_score)
    return 16 if base >= 80 else 11 if base >= 50 else 6


def _feasibility_score(candidate: OpportunityInput) -> int:
    if candidate.opportunity_type == "Software" and candidate.software_analysis:
        c = candidate.software_analysis.complexity
        points = 0
        points += {"LOW": 5, "MEDIUM": 3, "HIGH": 0, "UNKNOWN": 2}[c.development_complexity]
        points += {"LOW": 5, "MEDIUM": 3, "HIGH": 0, "UNKNOWN": 2}[c.infrastructure_complexity]
        points += {"LOW": 4, "MEDIUM": 2, "HIGH": 0, "UNKNOWN": 1}[c.ongoing_cost]
        points += {"HIGH": 6, "MEDIUM": 3, "LOW": 0, "UNKNOWN": 2}[c.solo_builder_fit]
        return min(20, points)
    return min(20, round(candidate.feasibility_score / 5))


def _actionability_score(candidate: OpportunityInput) -> int:
    physical = candidate.physical_analysis
    if physical and evaluate_final_deep_gate(physical).status == "HUMAN_REVIEW":
        physical = None
    analysis = candidate.software_analysis or physical
    if analysis:
        step = analysis.recommended_next_step
        return 5 if step in {"DROP", "WATCH"} else 15 if step == "READY_FOR_TEST" else 13
    if candidate.micro_innovation_score >= 75 and candidate.demand_score >= 70:
        return 13
    if candidate.micro_innovation_score >= 55:
        return 10
    return 5


def _freshness_score(created_at: str) -> int:
    if not created_at:
        return 1
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - parsed).days
        return 5 if days <= 7 else 3 if days <= 30 else 1
    except ValueError:
        return 1


def score_candidate(
    candidate: OpportunityInput, group_sources: dict[str, set[str]] | None = None
) -> RankedOpportunity:
    ai_quality, analysis_source, needs_analysis = _analysis_quality(candidate)
    independent = (group_sources or {}).get(candidate.opportunity_group or "", set())
    if len(independent) >= 2:
        cross = 5 if all("yanko" in source.casefold() for source in independent) else 10
        if any("yanko" in source.casefold() for source in independent):
            cross = min(cross, 5)
    else:
        cross = 0
    components = RankComponents(
        ai_quality=min(30, ai_quality),
        evidence=_evidence_score(candidate),
        feasibility=_feasibility_score(candidate),
        actionability=_actionability_score(candidate),
        cross_source=cross,
        freshness=_freshness_score(candidate.created_at),
    )
    return RankedOpportunity(candidate, min(100, components.total), components,
                             analysis_source, needs_analysis)


def apply_quality_gate(candidate: OpportunityInput) -> tuple[bool, str]:
    if candidate.triage is None or candidate.triage.provider != "gemini":
        return False, "missing_triage"
    if candidate.triage.triage_status == "REJECT":
        return False, "triage_reject"
    if candidate.triage.triage_status == "REVIEW":
        return False, "triage_review"
    risks = {risk.casefold() for risk in candidate.risk_flags + candidate.signals}
    if risks.intersection(HARD_RISKS):
        return False, "hard_risk"
    return True, ""


def _near_duplicate(left: OpportunityInput, right: OpportunityInput) -> bool:
    if left.opportunity_group and left.opportunity_group == right.opportunity_group:
        return True
    if left.theme != right.theme:
        return False
    tokens = lambda text: set(re.findall(r"[a-z0-9]+", text.casefold())) - {"the", "a", "for", "and", "of", "to"}
    a, b = tokens(left.title), tokens(right.title)
    return bool(a and b and len(a & b) / len(a | b) >= 0.65)


def _selection_reason(item: RankedOpportunity) -> str:
    c = item.candidate
    source = "Reddit demand" if "reddit" in c.source_platform.casefold() else (
        "Kickstarter validation" if "kickstarter" in c.source_platform.casefold() else
        "Amazon trend" if "amazon" in c.source_platform.casefold() else
        "creative inspiration" if "yanko" in c.source_platform.casefold() else "available evidence"
    )
    reason = f"{source} + personal feasibility + actionable next step; {item.analysis_source}."
    return reason[:160]


def select_daily_top(
    candidates: list[OpportunityInput], *, require_physical_analysis: bool = False
) -> DailyRankingResult:
    for candidate in candidates:
        candidate.theme = candidate.theme or infer_theme(candidate.title, candidate.summary)
        candidate.opportunity_group = candidate.opportunity_group or infer_opportunity_group(candidate.title, candidate.summary)
    group_sources: dict[str, set[str]] = {}
    for candidate in candidates:
        if candidate.opportunity_group:
            group_sources.setdefault(candidate.opportunity_group, set()).add(candidate.source_platform)
    scored = [score_candidate(candidate, group_sources) for candidate in candidates]
    scored.sort(key=lambda item: (-item.final_rank_score, item.candidate.title.casefold(), item.candidate.candidate_id))

    eligible, excluded = [], []
    for item in scored:
        passed, reason = apply_quality_gate(item.candidate)
        if passed:
            eligible.append(item)
        else:
            item.exclusion_reason = reason
            excluded.append(item)

    rejected_by_quality_gate = len(candidates) - len(eligible)
    eligible_before_specificity = len(eligible)
    specificity_counts = {"SPECIFIC": 0, "REVIEW": 0, "TOO_BROAD": 0}
    specificity_eligible: list[RankedOpportunity] = []
    removed_or_held: list[RankedOpportunity] = []
    for item in eligible:
        candidate = item.candidate
        if candidate.opportunity_type == "Software":
            specificity_eligible.append(item)
            continue
        item.specificity = assess_specificity(
            candidate.title, candidate.summary, candidate.signals,
            candidate.candidate_type, candidate.source_platform,
        )
        specificity_counts[item.specificity.specificity_status] += 1
        if (candidate.candidate_type == "demand_opportunity"
                and item.specificity.specificity_status == "TOO_BROAD"):
            item.exclusion_reason = "specificity_too_broad"
            excluded.append(item)
            removed_or_held.append(item)
        elif (candidate.candidate_type == "demand_opportunity"
              and item.specificity.specificity_status == "REVIEW"):
            item.exclusion_reason = "specificity_review"
            excluded.append(item)
            removed_or_held.append(item)
        else:
            specificity_eligible.append(item)
    eligible = specificity_eligible

    deep_gate_counts = {"PASS": 0, "REVIEW": 0, "DROP": 0, "HUMAN_REVIEW": 0}
    deep_eligible: list[RankedOpportunity] = []
    deep_gate_held_or_removed: list[RankedOpportunity] = []
    for item in eligible:
        candidate = item.candidate
        if candidate.opportunity_type != "Physical":
            deep_eligible.append(item)
            continue
        if candidate.physical_analysis is None:
            if require_physical_analysis:
                item.final_deep_gate = FinalDeepGateResult(
                    "HUMAN_REVIEW", "analysis_failed", [],
                )
                deep_gate_counts["HUMAN_REVIEW"] += 1
                item.exclusion_reason = "analysis_failed"
                excluded.append(item)
                deep_gate_held_or_removed.append(item)
            else:
                deep_eligible.append(item)
            continue
        item.final_deep_gate = evaluate_final_deep_gate(candidate.physical_analysis)
        deep_gate_counts[item.final_deep_gate.status] += 1
        if not require_physical_analysis and item.final_deep_gate.reason not in {
            "deep_drop", "high_regulatory_risk",
            "high_engineering_or_manufacturing_barrier",
        }:
            deep_eligible.append(item)
        elif item.final_deep_gate.status == "PASS":
            deep_eligible.append(item)
        else:
            item.exclusion_reason = item.final_deep_gate.reason
            excluded.append(item)
            deep_gate_held_or_removed.append(item)
    eligible = deep_eligible

    deduped: list[RankedOpportunity] = []
    near_removed = 0
    for item in eligible:
        if any(_near_duplicate(item.candidate, kept.candidate) for kept in deduped):
            item.exclusion_reason = "near_duplicate"
            excluded.append(item)
            near_removed += 1
        else:
            deduped.append(item)

    physical = [item for item in deduped if item.candidate.opportunity_type == "Physical"]
    software = [item for item in deduped if item.candidate.opportunity_type == "Software"]
    selected: list[RankedOpportunity] = []
    theme_counts: dict[str, int] = {}
    theme_removed = software_removed = 0

    def consider(item: RankedOpportunity, software_slot: bool = False) -> None:
        nonlocal theme_removed, software_removed
        if item.final_rank_score < MIN_FINAL_SCORE:
            item.exclusion_reason = "quality_score"
            excluded.append(item)
            return
        if len(selected) >= MAX_DAILY:
            item.exclusion_reason = "software_quota" if software_slot else "lower_final_score"
            software_removed += int(software_slot)
            excluded.append(item)
            return
        if theme_counts.get(item.candidate.theme, 0) >= MAX_PER_THEME:
            item.exclusion_reason = "theme_quota"
            theme_removed += 1
            excluded.append(item)
            return
        if software_slot and sum(x.candidate.opportunity_type == "Software" for x in selected) >= MAX_SOFTWARE:
            item.exclusion_reason = "software_quota"
            software_removed += 1
            excluded.append(item)
            return
        item.selection_reason = _selection_reason(item)
        selected.append(item)
        theme_counts[item.candidate.theme] = theme_counts.get(item.candidate.theme, 0) + 1

    for item in physical:
        consider(item)
    for item in software:
        consider(item, software_slot=True)

    for rank, item in enumerate(selected, 1):
        item.rank = rank
    selected_ids = {id(item) for item in selected}
    remaining = [item for item in scored if id(item) not in selected_ids]
    for item in remaining:
        if not item.exclusion_reason:
            item.exclusion_reason = "lower_final_score"
    remaining.sort(key=lambda item: (-item.final_rank_score, item.candidate.title.casefold()))
    for rank, item in enumerate(remaining[:10], 11):
        item.rank = rank
    return DailyRankingResult(
        eligible_candidates=len(eligible),
        rejected_by_quality_gate=rejected_by_quality_gate,
        physical_eligible=sum(x.candidate.opportunity_type == "Physical" for x in eligible),
        software_eligible=sum(x.candidate.opportunity_type == "Software" for x in eligible),
        near_duplicates_removed=near_removed,
        theme_quota_removed=theme_removed,
        software_quota_removed=software_removed,
        final=selected,
        next_ten=remaining[:10],
        eligible_before_specificity=eligible_before_specificity,
        removed_too_broad=sum(
            item.specificity is not None and item.specificity.specificity_status == "TOO_BROAD"
            for item in removed_or_held
        ),
        held_for_review=sum(
            item.specificity is not None and item.specificity.specificity_status == "REVIEW"
            for item in removed_or_held
        ),
        specificity_counts=specificity_counts,
        removed_or_held=removed_or_held,
        deep_gate_counts=deep_gate_counts,
        deep_gate_held_or_removed=deep_gate_held_or_removed,
    )


def select_full_qualified(candidates: list[OpportunityInput]) -> list[RankedOpportunity]:
    """Return every core-qualified opportunity without display quotas or score cutoff."""
    for candidate in candidates:
        candidate.theme = candidate.theme or infer_theme(candidate.title, candidate.summary)
        candidate.opportunity_group = candidate.opportunity_group or infer_opportunity_group(
            candidate.title, candidate.summary
        )
    group_sources: dict[str, set[str]] = {}
    for candidate in candidates:
        if candidate.opportunity_group:
            group_sources.setdefault(candidate.opportunity_group, set()).add(candidate.source_platform)

    qualified: list[RankedOpportunity] = []
    for candidate in candidates:
        passed, _ = apply_quality_gate(candidate)
        if not passed or not candidate.title.strip() or not candidate.source_url.strip():
            continue
        item = score_candidate(candidate, group_sources)
        if candidate.opportunity_type == "Physical":
            item.specificity = assess_specificity(
                candidate.title, candidate.summary, candidate.signals,
                candidate.candidate_type, candidate.source_platform,
            )
            if (candidate.candidate_type == "demand_opportunity"
                    and item.specificity.specificity_status != "SPECIFIC"):
                continue
            if candidate.physical_analysis:
                item.final_deep_gate = evaluate_final_deep_gate(candidate.physical_analysis)
                if item.final_deep_gate.reason in {
                    "deep_drop", "high_regulatory_risk",
                    "high_engineering_or_manufacturing_barrier",
                }:
                    continue
        qualified.append(item)
    qualified.sort(key=lambda item: (
        -item.final_rank_score,
        item.candidate.display_title.casefold(),
        item.candidate.candidate_id,
    ))
    for rank, item in enumerate(qualified, 1):
        item.rank = rank
        item.selection_reason = _selection_reason(item)
    return qualified


def load_current_opportunities() -> list[OpportunityInput]:
    """Read current normalized candidates and software records without network access."""
    products = {product.url: product for product in db.get_all_products()}
    candidate_rows = db.get_all_candidates()
    output: list[OpportunityInput] = []
    included_candidate_urls: set[str] = set()
    with db._connect() as connection:
        metadata = {
            row["url"]: row for row in connection.execute(
                """SELECT url, opportunity_type, risk_flags, positive_signals,
                   commodity_flags, created_at, raw_data, filter_score,
                   record_role FROM products"""
            ).fetchall()
        }
        for candidate in candidate_rows:
            row = metadata.get(candidate.source_url)
            product = products.get(candidate.source_url)
            if row and row["opportunity_type"] == "software":
                continue
            risk_value = row["risk_flags"] if row else []
            risks = risk_value if isinstance(risk_value, list) else json.loads(risk_value)
            triage = db.get_triage_result(candidate.candidate_id, "gemini", "gemini-3.5-flash-lite")
            physical = (db.get_deep_analysis_result(candidate.candidate_id, "gemini", "gemini-3.5-flash-lite", "v2")
                        or db.get_deep_analysis_result(candidate.candidate_id, "gemini", "gemini-3.5-flash-lite", "v1"))
            raw = product.raw_data if product else {}
            output.append(OpportunityInput(
                candidate_id=candidate.candidate_id, title=candidate.title,
                summary=candidate.summary, opportunity_type="Physical",
                candidate_type=candidate.candidate_type,
                source_platform=candidate.source_platform, source_url=candidate.source_url,
                candidate_score=candidate.candidate_score,
                feasibility_score=candidate.feasibility_score,
                demand_score=candidate.demand_score,
                market_validation_score=candidate.market_validation_score,
                micro_innovation_score=candidate.micro_innovation_score,
                signals=candidate.signals, risk_flags=risks, raw_data=raw,
                created_at=(row["created_at"].isoformat() if row and hasattr(row["created_at"], "isoformat") else (row["created_at"] if row else "")), triage=triage,
                physical_analysis=physical,
                theme=infer_theme(candidate.title, candidate.summary),
                opportunity_group=infer_opportunity_group(candidate.title, candidate.summary),
            ))
            included_candidate_urls.add(candidate.source_url)
        for url, row in metadata.items():
            if url in included_candidate_urls or not (row["record_role"] == "software" or row["opportunity_type"] == "software"):
                continue
            product = products[url]
            candidate_id = stable_candidate_id(product)
            triage = db.get_triage_result(candidate_id, "gemini", "gemini-3.5-flash-lite")
            software = db.get_software_analysis_result(candidate_id, "gemini", "gemini-3.5-flash-lite", "v1")
            output.append(OpportunityInput(
                candidate_id=candidate_id, title=product.title, summary=product.description,
                opportunity_type="Software", candidate_type="software",
                source_platform=product.source_platform, source_url=url,
                candidate_score=row["filter_score"], signals=[], risk_flags=[],
                raw_data=product.raw_data, created_at=(row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"]), triage=triage,
                software_analysis=software, theme="software",
                opportunity_group=infer_opportunity_group(product.title, product.description),
            ))
    return output


def select_triage_coverage_candidates(
    candidates: list[OpportunityInput], limit: int = 20, software_limit: int = 4
) -> list[OpportunityInput]:
    """Select one bounded physical-first batch lacking real Gemini triage."""
    limit = min(20, max(0, limit))
    software_limit = min(4, max(0, software_limit), limit)
    missing = [candidate for candidate in candidates if candidate.triage is None]
    group_sources: dict[str, set[str]] = {}
    for candidate in missing:
        if candidate.opportunity_group:
            group_sources.setdefault(candidate.opportunity_group, set()).add(candidate.source_platform)
    ranked = sorted(
        missing,
        key=lambda candidate: (
            -score_candidate(candidate, group_sources).final_rank_score,
            candidate.title.casefold(), candidate.candidate_id,
        ),
    )
    physical = [candidate for candidate in ranked if candidate.opportunity_type == "Physical"]
    complex_terms = {
        "infrastructure", "programming language", "enterprise platform",
        "security system", "model training", "data platform", "git forge",
        "managed ai agents", "internal ai agents", "memory infrastructure", "ide",
    }
    software = [
        candidate for candidate in ranked
        if candidate.opportunity_type == "Software"
        and len(candidate.summary.strip()) >= 30
        and not any(term in f"{candidate.title} {candidate.summary}".casefold() for term in complex_terms)
    ]
    chosen_software = software[:software_limit]
    physical_cap = min(16, limit - len(chosen_software))
    selected = physical[:physical_cap] + chosen_software
    if len(selected) < limit:
        selected_ids = {candidate.candidate_id for candidate in selected}
        selected.extend(
            candidate for candidate in physical[physical_cap:]
            if candidate.candidate_id not in selected_ids
        )
    return selected[:limit]


def to_triage_candidate(candidate: OpportunityInput) -> MicroInnovationCandidate:
    """Adapt an existing ranking candidate without changing the Candidate Pool."""
    return MicroInnovationCandidate(
        candidate_id=candidate.candidate_id,
        candidate_type=(candidate.candidate_type if candidate.candidate_type in {
            "demand_opportunity", "validated_product", "inspiration_product", "consumer_trend"
        } else "demand_opportunity"),
        source_platform=candidate.source_platform,
        source_url=candidate.source_url,
        title=candidate.title,
        summary=candidate.summary,
        candidate_score=candidate.candidate_score,
        feasibility_score=candidate.feasibility_score,
        demand_score=candidate.demand_score,
        market_validation_score=candidate.market_validation_score,
        micro_innovation_score=candidate.micro_innovation_score,
        reason="existing ranking candidate selected for bounded Gemini triage coverage",
        signals=candidate.signals,
        raw_reference_id=candidate.candidate_id,
    )
