"""Low-cost candidate-only AI triage orchestration."""

from dataclasses import dataclass
from html import unescape
import json
import re
from typing import Callable

import config
from ai_providers import AIProviderError, BaseAIProvider, GeminiProvider, MockAIProvider, OpenAIProvider
from candidate_pool import MicroInnovationCandidate
from models import AITriageResult, Product

MAX_BATCH = 20
MAX_DESCRIPTION = 500
REAL_API_TEST_LIMIT = 5
TRIAGE_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["triage_status", "triage_score", "confidence", "primary_reason", "opportunity_type", "key_opportunity", "main_risks", "needs_deep_analysis", "display_title_zh", "primary_reason_zh", "key_opportunity_zh", "main_risks_zh"],
    "properties": {
        "triage_status": {"type": "string", "enum": ["PASS", "REVIEW", "REJECT"]},
        "triage_score": {"type": "integer", "minimum": 1, "maximum": 10},
        "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "primary_reason": {"type": "string", "maxLength": 120},
        "opportunity_type": {"type": "string", "enum": ["product_improvement", "unmet_demand", "design_inspiration", "consumer_trend", "unknown"]},
        "key_opportunity": {"type": "string", "maxLength": 160},
        "main_risks": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 80}},
        "needs_deep_analysis": {"type": "boolean"},
        "display_title_zh": {"type": "string"},
        "primary_reason_zh": {"type": "string"},
        "key_opportunity_zh": {"type": "string"},
        "main_risks_zh": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
    },
}
SYSTEM_PROMPT = """Triage candidates for an individual or small team with under 10,000 RMB startup capital. Prefer small, lightweight, easy-to-ship, simple physical consumer products that may suit mature Chinese/1688 supply-chain research and low-cost micro-innovation. Reject food, supplements, medicine, cosmetics, regulated goods, complex electronics, wireless/Bluetooth products, high certification or tooling needs, large/heavy or fragile goods, weapons, IP copying, and proprietary technology. Food containers, bottles, and lunch boxes are not ingestible goods.

Use only evidence in the Candidate Input and the resource constraints above. Do not invent or present as verified any supplier or 1688 availability, MOQ, manufacturing cost, material cost, OEM ease, competition level, market size or growth, customer profession/demographics, IP status, certification, regulation, or export safety. If evidence is absent, say it requires validation or that no obvious signal appears in the input. Base primary_reason mainly on input evidence. key_opportunity may state a hypothesis, but label it with could, may, potential, or worth testing. A score of 10 requires strong evidence of feasibility, demand, validation, and differentiation; when supply chain, competition, or cost is unknown, generally cap at 8-9.

Return the same business judgment in concise English and natural, beginner-readable Simplified Chinese in one response. Chinese fields must not add facts, certainty, suppliers, MOQ, costs, market size, competition, customer profiles, certification, or regulation absent from the English/evidence. Keep primary_reason_zh within about 70 Chinese characters, key_opportunity_zh within about 90, and main_risks_zh to at most 3 items of about 45 characters each. display_title_zh must always be a non-empty, natural Simplified Chinese opportunity title of about 25 Chinese characters or fewer. Translate or faithfully summarize only the original title; do not add features or facts, do not use a mechanical word-by-word rendering, and never return null or an empty string. Return only compact JSON."""


@dataclass
class TriageBatchResult:
    eligible: int
    selected: int
    skipped_existing: int
    processed: list[AITriageResult]
    errors: int
    input_characters: list[int]


def build_triage_input(candidate: MicroInnovationCandidate, product: Product | None = None, commodity_score: int | None = None) -> dict:
    """Build a bounded allow-listed payload; raw_data is never included."""
    description = " ".join(unescape(re.sub(r"<[^>]+>", " ", candidate.summary)).split())[:MAX_DESCRIPTION]
    raw = product.raw_data if product else {}
    return {"candidate_type": candidate.candidate_type, "source_platform": candidate.source_platform, "title": candidate.title, "description": description, "category": product.category if product else "", "theme": "", "candidate_score": candidate.candidate_score, "feasibility_score": candidate.feasibility_score, "signal_score": candidate.demand_score, "commodity_score": commodity_score, "percent_funded": raw.get("percent_funded", raw.get("funding_percentage")), "backers_count": raw.get("backers_count", raw.get("backers")), "rank": raw.get("rank"), "rating": raw.get("rating"), "review_count": raw.get("review_count"), "signals": candidate.signals}


def select_diverse_candidates(candidates: list[MicroInnovationCandidate], limit: int = MAX_BATCH) -> list[MicroInnovationCandidate]:
    """Round-robin candidate types by score with a hard batch cap."""
    limit = min(MAX_BATCH, max(0, limit))
    types = ("validated_product", "demand_opportunity", "inspiration_product", "consumer_trend")
    groups = {kind: sorted((c for c in candidates if c.candidate_type == kind), key=lambda c: c.candidate_score, reverse=True) for kind in types}
    selected = []
    while len(selected) < limit and any(groups.values()):
        for kind in types:
            if groups[kind] and len(selected) < limit:
                selected.append(groups[kind].pop(0))
    return selected


def select_real_test_candidates(candidates: list[MicroInnovationCandidate]) -> list[MicroInnovationCandidate]:
    """Select the fixed five-item provider comparison mix when available."""
    quotas = (("demand_opportunity", 2), ("validated_product", 1), ("inspiration_product", 1), ("consumer_trend", 1))
    selected = []
    for kind, count in quotas:
        group = sorted((c for c in candidates if c.candidate_type == kind), key=lambda c: c.candidate_score, reverse=True)
        selected.extend(group[:count])
    if len(selected) < REAL_API_TEST_LIMIT:
        selected_ids = {c.candidate_id for c in selected}
        remainder = sorted((c for c in candidates if c.candidate_id not in selected_ids), key=lambda c: c.candidate_score, reverse=True)
        selected.extend(remainder[: REAL_API_TEST_LIMIT - len(selected)])
    return selected[:REAL_API_TEST_LIMIT]


def run_triage_batch(candidates: list[MicroInnovationCandidate], *, products: dict[str, Product] | None = None, commodity: dict[str, tuple[str, int]] | None = None, provider: BaseAIProvider | None = None, has_result: Callable[[str, str, str], bool] = lambda _id, _provider, _model: False, save_result: Callable[[AITriageResult], bool] = lambda _r: True, force_reanalyze: bool = False) -> TriageBatchResult:
    commodity = commodity or {}
    eligible = [c for c in candidates if c.candidate_type != "consumer_trend" or commodity.get(c.candidate_id, ("", 0))[0] == "PROMISING"]
    selected = select_diverse_candidates(eligible)
    provider = provider or MockAIProvider()
    processed = []
    skipped = errors = 0
    lengths = []
    for candidate in selected:
        if not force_reanalyze and has_result(
            candidate.candidate_id, provider.provider_name, provider.model_name
        ):
            skipped += 1
            continue
        payload = build_triage_input(candidate, (products or {}).get(candidate.source_url), commodity.get(candidate.candidate_id, ("", 0))[1])
        lengths.append(len(json.dumps(payload, ensure_ascii=False)))
        try:
            result = _parse_result(candidate.candidate_id, provider.analyze(payload, SYSTEM_PROMPT, TRIAGE_JSON_SCHEMA), provider)
            if force_reanalyze:
                try:
                    saved = save_result(result, force_reanalyze=True)
                except TypeError:
                    saved = save_result(result)
            else:
                saved = save_result(result)
            processed.append(result) if saved else None
            if result not in processed:
                errors += 1
        except (AIProviderError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            errors += 1
    return TriageBatchResult(len(eligible), len(selected), skipped, processed, errors, lengths)


def _parse_result(candidate_id: str, raw: str, provider: BaseAIProvider) -> AITriageResult:
    data = json.loads(raw)
    risks = data["main_risks"]
    if not isinstance(risks, list) or any(not isinstance(risk, str) for risk in risks):
        raise ValueError("invalid risks")
    status = data["triage_status"]
    status_ranges = {"PASS": (8, 10), "REVIEW": (5, 7), "REJECT": (1, 4)}
    if status not in status_ranges or not isinstance(data["triage_score"], int):
        raise ValueError("invalid triage status or score")
    minimum, maximum = status_ranges[status]
    score = max(minimum, min(maximum, data["triage_score"]))
    return AITriageResult(
        candidate_id=candidate_id,
        triage_status=status,
        triage_score=score,
        confidence=data["confidence"],
        primary_reason=data["primary_reason"][:120],
        opportunity_type=data["opportunity_type"],
        key_opportunity=data["key_opportunity"][:160],
        main_risks=[risk[:80] for risk in risks[:3]],
        needs_deep_analysis=data["needs_deep_analysis"],
        provider=provider.provider_name,
        model=provider.model_name,
        display_title_zh=data.get("display_title_zh"),
        primary_reason_zh=data.get("primary_reason_zh"),
        key_opportunity_zh=data.get("key_opportunity_zh"),
        main_risks_zh=[risk[:45] for risk in (data.get("main_risks_zh") or [])[:3]],
    )


def openai_dry_run(candidates: list[MicroInnovationCandidate], *, products: dict[str, Product] | None = None, commodity: dict[str, tuple[str, int]] | None = None, model: str = "gpt-5.4-nano") -> dict:
    """Build up to five final requests without invoking a client or network."""
    commodity = commodity or {}
    eligible = [c for c in candidates if c.candidate_type != "consumer_trend" or commodity.get(c.candidate_id, ("", 0))[0] == "PROMISING"]
    selected = select_diverse_candidates(eligible, REAL_API_TEST_LIMIT)
    provider = OpenAIProvider("", model, allow_unconfigured=True)
    lengths = []
    for candidate in selected:
        payload = build_triage_input(candidate, (products or {}).get(candidate.source_url), commodity.get(candidate.candidate_id, ("", 0))[1])
        request = provider.build_request(payload, SYSTEM_PROMPT, TRIAGE_JSON_SCHEMA)
        lengths.append(len(request["input"]))
    return {"model": model, "selected": selected, "input_characters": lengths, "request_ready": bool(selected) and bool(TRIAGE_JSON_SCHEMA), "network_request_sent": False}


def gemini_dry_run(candidates: list[MicroInnovationCandidate], *, products: dict[str, Product] | None = None, commodity: dict[str, tuple[str, int]] | None = None, model: str | None = None) -> dict:
    """Build up to five Gemini requests without invoking a client or network."""
    commodity = commodity or {}
    model = model or config.GEMINI_TRIAGE_MODEL
    eligible = [c for c in candidates if c.candidate_type != "consumer_trend" or commodity.get(c.candidate_id, ("", 0))[0] == "PROMISING"]
    selected = select_diverse_candidates(eligible, REAL_API_TEST_LIMIT)
    provider = GeminiProvider("", model, allow_unconfigured=True)
    lengths = []
    for candidate in selected:
        payload = build_triage_input(candidate, (products or {}).get(candidate.source_url), commodity.get(candidate.candidate_id, ("", 0))[1])
        request = provider.build_request(payload, SYSTEM_PROMPT, TRIAGE_JSON_SCHEMA)
        lengths.append(len(request["contents"]))
    return {"model": model, "selected": selected, "input_characters": lengths, "request_ready": bool(selected) and bool(TRIAGE_JSON_SCHEMA), "network_request_sent": False}
