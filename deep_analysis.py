"""Grounded, physical-product Deep Analysis MVP."""

from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import json
import re
from typing import Literal

from pydantic import BaseModel

from candidate_pool import MicroInnovationCandidate
from models import AITriageResult, Product


ANALYSIS_VERSION = "v2"
MAX_INPUT_CHARACTERS = 2500
MAX_OUTPUT_TOKENS = 800

Level = Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"]
NextStep = Literal[
    "DROP", "WATCH", "VALIDATE_DEMAND", "VALIDATE_SUPPLIER",
    "VALIDATE_COMPETITION", "DEEPER_RESEARCH", "READY_FOR_TEST",
]


class CheapTriageInput(BaseModel):
    status: Literal["PASS", "REVIEW", "REJECT"]
    score: int
    primary_reason: str
    key_opportunity: str
    main_risks: list[str]


class DeepAnalysisInput(BaseModel):
    candidate_id: str
    candidate_type: Literal[
        "demand_opportunity", "validated_product",
        "inspiration_product", "consumer_trend",
    ]
    source_platform: str
    title: str
    summary: str
    category: str
    candidate_score: int
    feasibility_score: int
    market_validation_score: int
    demand_score: int
    micro_innovation_score: int
    signals: list[str]
    source_metadata: dict[str, int | float | str]
    cheap_triage: CheapTriageInput


class Evidence(BaseModel):
    confirmed_evidence: list[str]
    hypotheses: list[str]


class SourcingDirection(BaseModel):
    search_keywords: list[str]
    supplier_type: list[str]
    manufacturing_category: list[str]
    supplier_questions: list[str]


class Feasibility(BaseModel):
    technical_complexity: Level
    manufacturing_complexity: Level
    shipping_friendliness: Level
    regulatory_risk: Level
    startup_cost_level: Level


class DeepAnalysisResponse(BaseModel):
    """Constraint-light schema sent to Gemini structured output."""

    opportunity_summary: str
    evidence: Evidence
    customer_problem: str
    existing_solution_gap: str
    micro_innovation_ideas: list[str]
    sourcing_direction: SourcingDirection
    validation_needed: list[str]
    feasibility: Feasibility
    content_marketing_angle: list[str]
    biggest_risks: list[str]
    recommended_next_step: NextStep
    deep_score: int


class DeepAnalysisResult(DeepAnalysisResponse):
    candidate_id: str
    provider: str
    model: str
    analysis_version: str = ANALYSIS_VERSION
    input_characters: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    created_at: str = ""
    updated_at: str = ""


DEEP_ANALYSIS_PROMPT = """Analyze one physical-product candidate for a solo seller or small team with under 10,000 RMB startup capital. Prefer small, lightweight, low-regulation, non-electronic products and incremental changes to structure, material, size, storage, portability, comfort, bundle, appearance, or use scenario. Do not propose complex invention or large-scale R&D.

Use only the supplied input. confirmed_evidence must contain explicit input facts; never mix hypotheses into it. existing_solution_gap may use only supplied evidence, otherwise say requires_validation. Hypotheses are testable directions, not permission to invent likely business facts. Never claim unverified supplier/1688 availability, easy sourcing, low MOQ, cheap or exact cost, margin, launch below 10,000 RMB, sales, market size, competition, demographics, certification, regulation, patents, or demand. Missing facts require validation. Multiple brands, compared products, review counts, or rankings support only statements such as established products exist, multiple recognizable brands appear in the current evidence, or the category appears mature from current examples; competition requires validation. Without explicit market data, never say market dominated, highly saturated, low competition, blue ocean, market leaders dominate, huge market, or strong market growth. Sourcing is SEARCH DIRECTION ONLY - NOT VERIFIED SUPPLIERS. Hypotheses must say may, could, potential, worth searching/testing, or requires validation.

For feasibility, use UNKNOWN when supplier, MOQ, cost, manufacturing, size, or weight evidence is absent. Do not infer LOW startup cost from simple structure. LOW regulatory risk means only no obvious signal in current input, not verified certification. Choose recommended_next_step from the largest unknown. Scores 9-10 require relatively complete evidence and a clear action path.

For demand_opportunity analyze problem to product; validated_product analyze incremental improvement; inspiration_product analyze low-cost translation; consumer_trend analyze differentiated space without treating rank as sales. Return decision-support JSON, not a report. Use one short sentence per item: at most 3 confirmed_evidence, 3 hypotheses, 3 micro_innovation_ideas, 5 validation_needed, 5 supplier_questions, 3 content_marketing_angle, and 3 biggest_risks. deep_score is 1-10. Target 500-700 output tokens and never exceed 800."""


def _clean(text: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", text)).split())


def serialize_input(value: DeepAnalysisInput) -> str:
    return json.dumps(value.model_dump(), ensure_ascii=False, separators=(",", ":"))


def build_deep_analysis_input(
    candidate: MicroInnovationCandidate,
    triage: AITriageResult,
    product: Product | None = None,
    commodity_score: int | None = None,
) -> DeepAnalysisInput:
    """Build an allow-listed input and preserve core evidence within 2,500 chars."""
    raw = product.raw_data if product else {}
    metadata_keys = (
        "percent_funded", "funding_percentage", "backers_count", "backers",
        "rank", "rank_change", "rating", "review_count",
    )
    metadata = {
        key: raw[key] for key in metadata_keys
        if raw.get(key) is not None and isinstance(raw[key], (int, float, str))
    }
    if commodity_score is not None:
        metadata["commodity_score"] = commodity_score
    summary = _clean(candidate.summary)[:1400]
    value = DeepAnalysisInput(
        candidate_id=candidate.candidate_id,
        candidate_type=candidate.candidate_type,
        source_platform=candidate.source_platform,
        title=_clean(candidate.title),
        summary=summary,
        category=product.category if product else "",
        candidate_score=candidate.candidate_score,
        feasibility_score=candidate.feasibility_score,
        market_validation_score=candidate.market_validation_score,
        demand_score=candidate.demand_score,
        micro_innovation_score=candidate.micro_innovation_score,
        signals=candidate.signals,
        source_metadata=metadata,
        cheap_triage=CheapTriageInput(
            status=triage.triage_status,
            score=triage.triage_score,
            primary_reason=triage.primary_reason,
            key_opportunity=triage.key_opportunity,
            main_risks=triage.main_risks,
        ),
    )
    while len(serialize_input(value)) > MAX_INPUT_CHARACTERS and len(value.summary) > 300:
        value.summary = value.summary[:-100]
    if len(serialize_input(value)) > MAX_INPUT_CHARACTERS:
        value.source_metadata = {}
    if len(serialize_input(value)) > MAX_INPUT_CHARACTERS:
        value.signals = value.signals[:5]
    if len(serialize_input(value)) > MAX_INPUT_CHARACTERS:
        raise ValueError("Deep Analysis input exceeds 2500 characters")
    return value


def parse_deep_analysis_result(
    candidate_id: str,
    raw: str,
    provider: str,
    model: str,
    input_characters: int,
    usage: dict[str, int] | None = None,
    has_verified_supplier_cost_data: bool = False,
) -> DeepAnalysisResult:
    """Normalize provider output into the shared, bounded business result."""
    response = DeepAnalysisResponse.model_validate_json(raw)
    now = datetime.now(timezone.utc).isoformat()
    evidence = response.evidence.model_copy(update={
        "confirmed_evidence": response.evidence.confirmed_evidence[:3],
        "hypotheses": response.evidence.hypotheses[:3],
    })
    sourcing = response.sourcing_direction.model_copy(update={
        "supplier_questions": response.sourcing_direction.supplier_questions[:5],
    })
    feasibility = response.feasibility
    if not has_verified_supplier_cost_data:
        updates = {}
        if feasibility.startup_cost_level == "LOW":
            updates["startup_cost_level"] = "UNKNOWN"
        if feasibility.manufacturing_complexity == "LOW":
            updates["manufacturing_complexity"] = "UNKNOWN"
        if updates:
            feasibility = feasibility.model_copy(update=updates)
    return DeepAnalysisResult(
        **response.model_dump(exclude={
            "evidence", "sourcing_direction", "validation_needed",
            "feasibility", "micro_innovation_ideas",
            "content_marketing_angle", "biggest_risks", "deep_score",
        }),
        evidence=evidence,
        sourcing_direction=sourcing,
        validation_needed=response.validation_needed[:5],
        feasibility=feasibility,
        micro_innovation_ideas=response.micro_innovation_ideas[:3],
        content_marketing_angle=response.content_marketing_angle[:3],
        biggest_risks=response.biggest_risks[:3],
        deep_score=max(1, min(10, response.deep_score)),
        candidate_id=candidate_id,
        provider=provider,
        model=model,
        analysis_version=ANALYSIS_VERSION,
        input_characters=input_characters,
        input_tokens=(usage or {}).get("input_tokens"),
        output_tokens=(usage or {}).get("output_tokens"),
        total_tokens=(usage or {}).get("total_tokens"),
        created_at=now,
        updated_at=now,
    )


def detect_unsupported_claims(result: DeepAnalysisResult) -> list[str]:
    """Apply a deterministic phrase check; this is not an AI judgment."""
    text = json.dumps(result.model_dump(), ensure_ascii=False).casefold()
    checks = {
        "confirmed supplier": r"confirmed supplier|supplier (?:is|has been) confirmed",
        "low MOQ": r"(?:extremely |very )?low moq",
        "exact cost": r"(?:unit|manufacturing|material|purchase) cost (?:is|of|at) [¥$€£]?\d",
        "guaranteed margin": r"guaranteed margin|margin is guaranteed",
        "huge market": r"huge market|massive market|dominat(?:e|es|ed|ing).{0,80}market",
        "low competition": r"low competition|competition is low|no competition",
        "certification confirmed": r"certification (?:is|has been) confirmed",
        "patent safe": r"patent safe|no patent risk",
        "guaranteed demand": r"guaranteed demand|demand is guaranteed",
    }
    return [label for label, pattern in checks.items() if re.search(pattern, text)]
