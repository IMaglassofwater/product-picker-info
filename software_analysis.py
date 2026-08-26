"""Lightweight, grounded software-opportunity analysis MVP."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
import json
import re
from typing import Literal

from pydantic import BaseModel

from models import Product


ANALYSIS_VERSION = "v1"
MAX_INPUT_CHARACTERS = 2000
MAX_OUTPUT_TOKENS = 500

Level = Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"]
SoloFit = Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]
NextStep = Literal[
    "DROP", "WATCH", "VALIDATE_DEMAND", "VALIDATE_IMPLEMENTATION",
    "VALIDATE_COMPETITION", "DEEPER_RESEARCH", "READY_FOR_TEST",
]
Interface = Literal["web_app", "browser_extension", "automation", "api_tool", "other"]
Monetization = Literal[
    "subscription", "one_time_purchase", "freemium",
    "usage_based", "lead_generation",
]


class SoftwareAnalysisInput(BaseModel):
    candidate_id: str
    source_platform: str
    title: str
    summary: str
    category: str
    existing_score: int | None
    signals: list[str]


class ImplementationPath(BaseModel):
    possible_interfaces: list[Interface]
    possible_building_blocks: list[str]
    unknowns: list[str]


class OpenSourceOrAILeverage(BaseModel):
    search_direction: list[str]
    possible_leverage: list[str]
    validation_needed: list[str]


class SoftwareComplexity(BaseModel):
    development_complexity: Level
    ongoing_cost: Level
    infrastructure_complexity: Level
    solo_builder_fit: SoloFit


class SoftwareAnalysisResponse(BaseModel):
    """Constraint-light Gemini schema for the 14 software analysis modules."""

    opportunity_summary: str
    confirmed_evidence: list[str]
    hypotheses: list[str]
    user_problem: str
    existing_solution_gap: str
    mvp_idea: list[str]
    implementation_path: ImplementationPath
    open_source_or_ai_leverage: OpenSourceOrAILeverage
    monetization_direction: list[Monetization]
    validation_needed: list[str]
    acquisition_angle: list[str]
    biggest_risks: list[str]
    recommended_next_step: NextStep
    software_score: int
    complexity: SoftwareComplexity


class SoftwareAnalysisResult(SoftwareAnalysisResponse):
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


SOFTWARE_ANALYSIS_PROMPT = """Analyze one software opportunity for a solo builder or small team. Favor a narrow simple web app, browser extension, AI utility, workflow automation, niche productivity or creator/B2B tool that can test one clear problem. Lower complex AI training, high GPU use, large platforms, security/compliance-heavy systems, enterprise infrastructure, and large data platforms.

Use only supplied input. confirmed_evidence contains explicit facts; hypotheses must say may, could, worth testing, or requires_validation. Never invent an existing GitHub repository, confirmed API/open-source availability, development time or cost, willingness to pay, ARR, market size, competition, conversion, acquisition cost, security, or compliance. Named APIs, models, libraries, open-source, AI coding, and serverless are SEARCH DIRECTIONS ONLY until verified.

mvp_idea contains at most 3 essential features for one testable outcome, never a full platform. implementation_path may suggest possible interfaces/building blocks but must list technical unknowns. open_source_or_ai_leverage contains search_direction, possible_leverage, and validation_needed; do not invent repo names. Monetization directions are hypotheses, not monetization evidence, and cannot include unverified prices. Use UNKNOWN for unsupported complexity judgments. Choose the next step from the largest unknown.

Calibrate software_score using evidence strength, user-problem clarity, MVP simplicity, solo-builder fit, differentiation potential, demand validation, monetization evidence, technical/data dependencies, usage-frequency or retention risk, and competition unknowns. Scores 6-7 mean worth validating with important commercial unknowns; 8 requires strong demand evidence and only a few key validations; 9 requires multiple evidence dimensions including some commercial validation. Score 10 is extremely rare and requires strong current evidence for demand, pain, execution, differentiation, and commercial viability with few major unknowns. VALIDATE_DEMAND without strong demand evidence is usually no higher than 7; multiple unknowns around willingness to pay, competition, and API/data availability usually rule out 8+. This is calibration, not a mechanical hard cap. DROP should not score highly, and READY_FOR_TEST does not imply 9-10. Low development complexity, low infrastructure cost, AI coding, or high solo-builder fit show only that an idea may be easier to build; technical simplicity does not equal a validated business opportunity.

Return compact structured JSON under 500 tokens with short phrases and no repeated background."""


def _clean(text: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", text)).split())


def stable_candidate_id(product: Product) -> str:
    return sha256(product.url.encode("utf-8")).hexdigest()[:24]


def serialize_input(value: SoftwareAnalysisInput) -> str:
    return json.dumps(value.model_dump(), ensure_ascii=False, separators=(",", ":"))


def build_software_analysis_input(
    product: Product,
    *,
    existing_score: int | None = None,
    signals: list[str] | None = None,
) -> SoftwareAnalysisInput:
    summary = _clean(product.description)[:1400]
    value = SoftwareAnalysisInput(
        candidate_id=stable_candidate_id(product),
        source_platform=product.source_platform,
        title=_clean(product.title),
        summary=summary,
        category=product.category,
        existing_score=existing_score,
        signals=(signals or [])[:10],
    )
    while len(serialize_input(value)) > MAX_INPUT_CHARACTERS and len(value.summary) > 300:
        value.summary = value.summary[:-100]
    if len(serialize_input(value)) > MAX_INPUT_CHARACTERS:
        value.signals = value.signals[:5]
    if len(serialize_input(value)) > MAX_INPUT_CHARACTERS:
        raise ValueError("Software Analysis input exceeds 2000 characters")
    return value


def parse_software_analysis_result(
    candidate_id: str,
    raw: str,
    provider: str,
    model: str,
    input_characters: int,
    usage: dict[str, int] | None = None,
) -> SoftwareAnalysisResult:
    response = SoftwareAnalysisResponse.model_validate_json(raw)
    now = datetime.now(timezone.utc).isoformat()
    leverage = response.open_source_or_ai_leverage.model_copy(update={
        "search_direction": response.open_source_or_ai_leverage.search_direction[:3],
        "possible_leverage": response.open_source_or_ai_leverage.possible_leverage[:3],
        "validation_needed": response.open_source_or_ai_leverage.validation_needed[:3],
    })
    return SoftwareAnalysisResult(
        **response.model_dump(exclude={
            "confirmed_evidence", "hypotheses", "mvp_idea",
            "open_source_or_ai_leverage", "monetization_direction",
            "validation_needed", "acquisition_angle", "biggest_risks",
            "software_score",
        }),
        confirmed_evidence=response.confirmed_evidence[:3],
        hypotheses=response.hypotheses[:3],
        mvp_idea=response.mvp_idea[:3],
        open_source_or_ai_leverage=leverage,
        monetization_direction=response.monetization_direction[:2],
        validation_needed=response.validation_needed[:5],
        acquisition_angle=response.acquisition_angle[:3],
        biggest_risks=response.biggest_risks[:3],
        software_score=max(1, min(10, response.software_score)),
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


def detect_unsupported_claims(result: SoftwareAnalysisResult) -> list[str]:
    text = json.dumps(result.model_dump(), ensure_ascii=False).casefold()
    checks = {
        "confirmed API": r"(?:api availability|api) (?:is|has been) confirmed|confirmed api",
        "existing GitHub repository": r"existing github repositor|github repo (?:exists|is available)",
        "exact development cost": r"(?:development|build) cost (?:is|of|at) [¥$€£]?\d",
        "exact development time": r"(?:development|build) (?:time|takes|will take) (?:is )?\d+ (?:day|week|month)",
        "large market": r"huge market|massive market|large market",
        "low competition": r"low competition|competition is low|no competition",
        "guaranteed willingness to pay": r"guaranteed willingness to pay|users (?:will|are willing to) pay",
    }
    return [label for label, pattern in checks.items() if re.search(pattern, text)]
