"""Selection and safe merge helpers for future bilingual triage enrichment."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json

from pydantic import BaseModel

import db
from daily_ranker import OpportunityInput, load_current_opportunities
from models import AITriageResult


PROVIDER = "gemini"
MODEL = "gemini-3.5-flash-lite"

ENRICHMENT_PROMPT = """Convert only the supplied existing English triage presentation into concise natural Simplified Chinese. This is translation/enrichment only, not a new product judgment. Do not rescore, reclassify, add facts, infer suppliers, MOQ, costs, competition, market size, customer profiles, certification, regulation, or availability. Preserve uncertainty exactly: requires validation must remain requires validation. Return only the four requested Chinese fields. Keep display_title_zh within about 25 Chinese characters, primary_reason_zh within about 70, key_opportunity_zh within about 90, and main_risks_zh to at most 3 compact items."""


class BilingualEnrichmentResponse(BaseModel):
    display_title_zh: str
    primary_reason_zh: str
    key_opportunity_zh: str
    main_risks_zh: list[str]


@dataclass(frozen=True)
class BilingualEnrichment:
    display_title_zh: str | None
    primary_reason_zh: str
    key_opportunity_zh: str
    main_risks_zh: list[str]


def build_enrichment_input(title: str, result: AITriageResult) -> dict:
    """Allow-list only existing English presentation; no candidate raw data."""
    return {
        "original_title": title,
        "primary_reason": result.primary_reason,
        "key_opportunity": result.key_opportunity,
        "main_risks": result.main_risks,
    }


def parse_enrichment(raw: str) -> BilingualEnrichment:
    data = BilingualEnrichmentResponse.model_validate_json(raw)
    return BilingualEnrichment(
        display_title_zh=data.display_title_zh[:25] or None,
        primary_reason_zh=data.primary_reason_zh[:70],
        key_opportunity_zh=data.key_opportunity_zh[:90],
        main_risks_zh=[risk[:45] for risk in data.main_risks_zh[:3]],
    )


def needs_bilingual_backfill(result: AITriageResult) -> bool:
    return not (
        result.primary_reason_zh
        and result.key_opportunity_zh
        and result.main_risks_zh
    )


def select_bilingual_backfill(
    opportunities: list[OpportunityInput] | None = None,
) -> list[tuple[OpportunityInput, AITriageResult]]:
    """Select only real Gemini triage rows whose Chinese fields are incomplete."""
    selected = []
    for opportunity in opportunities if opportunities is not None else load_current_opportunities():
        result = db.get_triage_result(opportunity.candidate_id, PROVIDER, MODEL)
        if result is not None and needs_bilingual_backfill(result):
            selected.append((opportunity, result))
    return selected


def merge_bilingual_enrichment(
    original: AITriageResult, enrichment: BilingualEnrichment,
) -> AITriageResult:
    """Add only bilingual fields; the original judgment can never change."""
    return replace(
        original,
        display_title_zh=enrichment.display_title_zh,
        primary_reason_zh=enrichment.primary_reason_zh,
        key_opportunity_zh=enrichment.key_opportunity_zh,
        main_risks_zh=enrichment.main_risks_zh[:3],
    )


def save_bilingual_enrichment(
    original: AITriageResult, enrichment: BilingualEnrichment,
) -> bool:
    merged = merge_bilingual_enrichment(original, enrichment)
    if (merged.triage_status, merged.triage_score) != (
        original.triage_status, original.triage_score
    ):
        return False
    return db.save_triage_result(merged, force_reanalyze=True)
