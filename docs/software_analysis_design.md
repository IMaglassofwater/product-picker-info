# Lightweight Software Analysis Design

## Purpose

Lightweight Software Analysis evaluates whether a software or digital opportunity is suitable for a solo builder or small team to validate cheaply. It is an auxiliary track, not a replacement for Product Picker's physical-product focus.

The analysis favors narrow problems, small MVPs, AI or open-source leverage, browser tools, workflow automation, micro-productivity tools, creator utilities, niche B2B tools, and simple SaaS. It lowers or rejects infrastructure-heavy platforms, high-security or high-compliance systems, custom model training, compute-intensive products, and enterprise-scale engineering.

It never uses physical-product fields such as 1688, MOQ, suppliers, manufacturing, materials, or shipping.

## Candidate Eligibility

A software candidate is eligible only when:

- Cheap Triage status is `PASS`.
- The source describes a specific user problem or workflow gap.
- A plausible MVP does not require a large engineering team, heavy infrastructure, or major capital.
- Lightweight Software Analysis later assigns a score at or above the configured publication threshold.

Eligibility is not publication. Daily selection may publish zero software opportunities when none meet the quality bar.

## Input

`SoftwareAnalysisInput` is an allow-listed payload built from existing records:

```text
candidate_id
candidate_type
source_platform
title
summary
candidate_score
demand_score
micro_innovation_score
signals
available product/category metadata
Cheap Triage status, score, reason, opportunity, and risks
```

Full `raw_data`, complete threads, HTML, external webpages, and unrelated database history are excluded. Missing metadata is omitted. The serialized input must not exceed 2,000 characters; retain the explicit user problem and evidence before secondary scores or metadata.

## Output Schema

`SoftwareAnalysisResult` contains 14 compact sections:

```text
opportunity_summary: str
confirmed_evidence: list[str]
hypotheses: list[str]
user_problem: str
existing_solution_gap: str
mvp_idea: str
implementation_path:
  possible_interfaces: list[web_app | browser_extension | automation | api_tool | other]
  possible_building_blocks: list[str]
  unknowns: list[str]
open_source_or_ai_leverage:
  possible_directions: list[str]
  validation_needed: list[str]
monetization_direction: list[subscription | one_time_purchase | freemium |
                             usage_based | lead_generation]
validation_needed: list[str]
acquisition_angle: list[str]
biggest_risks: list[str]
recommended_next_step: DROP | WATCH | VALIDATE_DEMAND |
                       VALIDATE_IMPLEMENTATION | VALIDATE_COMPETITION |
                       DEEPER_RESEARCH | READY_FOR_TEST
software_score: int  # 1-10
complexity:
  development_complexity: LOW | MEDIUM | HIGH | UNKNOWN
  ongoing_cost: LOW | MEDIUM | HIGH | UNKNOWN
  infrastructure_complexity: LOW | MEDIUM | HIGH | UNKNOWN
  solo_builder_fit: HIGH | MEDIUM | LOW | UNKNOWN
```

Provider/model/version and timestamps belong to persistence metadata rather than AI-generated business evidence.

## Grounding

- `confirmed_evidence` contains only explicit input facts.
- `hypotheses` and proposed directions use “may,” “could,” “worth testing,” or `requires_validation`.
- Never invent market size, ARR, conversion rate, willingness to pay, competition level, development time, development cost, API availability, open-source availability, security posture, compliance status, or customer demographics.
- Mentioning an API, model, framework, or GitHub/open-source direction is not proof that it is available, licensed appropriately, affordable, or technically sufficient.
- If evidence is absent, use `requires_validation` or `UNKNOWN`.
- Rankings, comments, and discussions are signals only; they are not exact usage, revenue, or demand.

## Complexity Scoring

Each complexity label is an initial evidence-bounded judgment:

- `development_complexity`: breadth of product logic, integrations, data, and frontend/backend work described by the input.
- `ongoing_cost`: likely operational cost category; use `UNKNOWN` without verified workload and provider pricing.
- `infrastructure_complexity`: deployment, storage, realtime, compute, and reliability requirements visible in the input.
- `solo_builder_fit`: whether the described scope appears bounded enough for one person or a small team; this is not a delivery-time estimate.

High-security, regulated, compute-heavy, foundation-infrastructure, or multi-sided platform requirements should reduce `solo_builder_fit`. Unknown technical dependencies remain `UNKNOWN` rather than being assumed easy.

## MVP Evaluation

The analysis asks whether an MVP could be framed as one narrow workflow using possible directions such as an existing API, open-source component, hosted model, browser extension, simple web app, or automation tool.

It must identify:

- the smallest testable user outcome;
- essential versus optional capabilities;
- integrations and technical assumptions requiring verification;
- whether a manual or concierge test could precede software development;
- security, privacy, compliance, and infrastructure unknowns.

No named project, API, or model is described as usable until separately verified.

## Monetization Hypotheses

Allowed directions are subscription, one-time purchase, freemium, usage-based, and lead generation. They are hypotheses only. The analysis must not state a price, willingness to pay, conversion rate, margin, ARR, or revenue expectation without input evidence.

The selected direction should be tied to the product's usage pattern and followed by a concrete validation question.

## Token Budget

- Input: no more than 2,000 characters.
- Output: no more than 500 tokens.
- Keep confirmed evidence, hypotheses, acquisition angles, risks, and validations short and deduplicated.
- Prefer one concise sentence or phrase per item.
- Do not repeat the candidate background across sections.

## Daily Top 10 Integration

- Publish at most 10 total opportunities per day.
- Physical opportunities are always the primary track.
- Software opportunities are capped at 2 per day; this is not a fixed 8+2 allocation.
- Software volume must never displace stronger physical candidates.
- Only Cheap Triage `PASS` candidates meeting the future `software_score` threshold are eligible.
- Zero software opportunities is valid. Never force-fill the daily list.

## Example

Illustrative candidate name from the current database: `App that recommends smart fabric choices for one-bag travel based on destination and weather?`

This is a schema example only, not a real Deep Analysis and not an API result:

```json
{
  "opportunity_summary": "Explore a narrowly scoped tool that helps users compare fabric considerations for a stated travel scenario.",
  "confirmed_evidence": [
    "The candidate title asks for fabric recommendations based on destination and weather."
  ],
  "hypotheses": [
    "A simple guided comparison could be worth testing before building an automated recommendation engine."
  ],
  "user_problem": "The input suggests uncertainty when matching travel fabric choices to conditions.",
  "existing_solution_gap": "requires_validation",
  "mvp_idea": "Test a short questionnaire with rule-based comparison output.",
  "implementation_path": {
    "possible_interfaces": ["web_app"],
    "possible_building_blocks": ["rule-based questionnaire"],
    "unknowns": ["weather-data requirements and API availability require validation"]
  },
  "open_source_or_ai_leverage": {
    "possible_directions": ["A hosted model or open-source component may help summarize supplied fabric attributes."],
    "validation_needed": ["licensing, accuracy, API availability, and cost"]
  },
  "monetization_direction": ["freemium"],
  "validation_needed": ["problem frequency", "data requirements", "willingness to pay", "competition"],
  "acquisition_angle": ["Demonstrate two contrasting packing scenarios."],
  "biggest_risks": ["Reliable recommendation data and demand are unverified."],
  "recommended_next_step": "VALIDATE_DEMAND",
  "software_score": 5,
  "complexity": {
    "development_complexity": "UNKNOWN",
    "ongoing_cost": "UNKNOWN",
    "infrastructure_complexity": "UNKNOWN",
    "solo_builder_fit": "UNKNOWN"
  }
}
```
