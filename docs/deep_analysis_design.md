# Product Picker Deep Analysis Design

## Purpose

Deep Analysis is the second AI stage after Cheap Triage. It answers: why an opportunity may be worth pursuing, what a solo seller or small team could test, and which facts still require validation.

It is designed for small, lightweight, low-regulation physical consumer products, modest startup capital, mature manufacturing categories, incremental product changes, cross-border ecommerce, and content-led testing. It must not turn weak evidence into a recommendation for complex hardware, high tooling investment, heavy goods, weapons, medical products, or pure brand competition.

## Input

`DeepAnalysisInput` is an allow-listed payload assembled from existing database fields. Raw source payloads are never sent wholesale.

```text
DeepAnalysisInput
  candidate_id: str
  candidate_type: demand_opportunity | validated_product |
                  inspiration_product | consumer_trend
  source_platform: str
  title: str
  summary: str
  category: str | null
  candidate_score: int
  feasibility_score: int
  market_validation_score: int
  demand_score: int
  micro_innovation_score: int
  signals: list[str]
  source_metadata:
    percent_funded: number | null
    backers_count: int | null
    rank: int | null
    rank_change: number | null
    rating: number | null
    review_count: int | null
  cheap_triage:
    status: PASS | REVIEW | REJECT
    score: int
    confidence: HIGH | MEDIUM | LOW
    opportunity_type: str
    primary_reason: str
    key_opportunity: str
    main_risks: list[str]
```

Only metadata actually present in the database is included. Null fields may be omitted. Source text is normalized and length-bounded. The builder should prioritize the candidate summary, signals, Cheap Triage result, and source-specific evidence relevant to the candidate type.

## Output Schema

All providers must normalize into one `DeepAnalysisResult` business model.

```text
DeepAnalysisResult
  candidate_id: str
  opportunity_summary: str
  evidence:
    confirmed_evidence: list[str]
    hypotheses: list[str]
  customer_problem: str
  existing_solution_gap: str
  micro_innovation_ideas: list[str]          # maximum 3
  sourcing_direction:
    search_keywords: list[str]
    supplier_type: list[str]
    likely_manufacturing_category: list[str]
    supplier_questions: list[str]
  validation_needed: list[str]
  feasibility:
    technical_complexity: LOW | MEDIUM | HIGH
    manufacturing_complexity: LOW | MEDIUM | HIGH
    shipping_friendliness: LOW | MEDIUM | HIGH
    regulatory_risk: LOW | MEDIUM | HIGH
    startup_cost_level: LOW | MEDIUM | HIGH
  content_marketing_angles: list[str]        # maximum 3
  biggest_risks: list[str]                   # maximum 3
  recommended_next_step: DROP | WATCH | VALIDATE_DEMAND |
                         VALIDATE_SUPPLIER | VALIDATE_COMPETITION |
                         DEEPER_RESEARCH | READY_FOR_TEST
  deep_score: int                            # 1-10
  provider: str
  model: str
  analysis_version: str
  analyzed_at: str
```

The response schema should enforce types, enums, required fields, and arrays. Length, item-count, score, and status consistency should also be validated after the provider returns. Provider-specific schema representations may differ, but the business fields must remain identical.

## Prompt Structure

The Deep Analysis prompt has five compact blocks:

1. Role and resource constraints: analyze for a solo seller or small team with limited capital.
2. Candidate-type instruction: apply the correct analysis emphasis for the input type.
3. Grounding contract: separate confirmed evidence from hypotheses and mark absent facts as requiring validation.
4. Analysis tasks: produce the defined sections, favoring incremental physical-product improvements and practical validation.
5. Output contract: return only the structured result, within limits and without citations or facts not present in the input.

The prompt must explicitly say that search keywords and supplier categories are research directions, not proof of supplier availability, MOQ, cost, or manufacturability.

## Candidate-Type Differences

| Candidate type | Primary question | Evidence emphasis | Required caution |
|---|---|---|---|
| `demand_opportunity` | Can an expressed problem become a practical product opportunity? | Problem statement, use scenario, explicit feature gaps, demand signals | A request or discussion is not market-size proof |
| `validated_product` | What evidence-backed, incremental improvement could be tested on an existing product? | Product attributes, observed shortcomings, funding/backer evidence when present | Validation of the existing product does not validate a proposed modification |
| `inspiration_product` | Can the creative idea be translated into a simpler, affordable physical product? | Published concept details and low-complexity design signals | Editorial attention is not demand or manufacturing validation |
| `consumer_trend` | Is there a differentiated micro-innovation angle within the observed trend? | Rank, rank change, ratings, reviews, and list source when present | Rank is not exact sales; popularity does not prove an accessible market gap |

## Grounding Rules

- `confirmed_evidence` may contain only facts present in `DeepAnalysisInput`.
- `hypotheses` must use uncertain language such as “could,” “may,” “potential,” or “worth testing.”
- Never invent supplier availability, MOQ, manufacturing or unit cost, sales volume, market size, competition level, demographics, certification status, regulatory status, patents, or export suitability.
- Source metadata may be interpreted only within its meaning. Funding, backers, rank, reviews, and demand signals must not be expanded into unsupported market claims.
- When evidence is missing, state `requires_validation` in the relevant section.
- `primary_reason`-style conclusions must be traceable to supplied evidence. Sourcing terms are search directions only.
- A high `deep_score` requires multiple strong evidence dimensions; simple construction alone is insufficient.

## Token Budget

- Serialized input target: no more than 2,500 characters per candidate.
- Output target: about 500-700 tokens, with an 800-token ceiling per candidate.
- Do not send complete `raw_data`, full articles, full Reddit threads, HTML, or repeated fields.
- Keep confirmed evidence, hypotheses, validations, risks, keywords, and supplier questions concise and deduplicated.
- `micro_innovation_ideas`, `content_marketing_angles`, and `biggest_risks` are capped at three items each.

## Provider Call Design

The execution layer reuses the selected AI provider abstraction with a Deep Analysis system prompt and provider-compatible structured-output schema. It should:

1. Build and measure the allow-listed input.
2. Reject or trim input above 2,500 characters before any API call.
3. Check the composite result key before calling the provider.
4. Make one structured-output request with bounded timeout and retry behavior.
5. Normalize and validate the response into `DeepAnalysisResult` without another AI call.
6. Save the validated result and usage metadata; contain per-candidate failures.

Cheap Triage and Deep Analysis remain separate calls and separate stored results. Only candidates explicitly selected for deeper research should enter this flow.

## Database Design

Suggested table: `ai_deep_analysis_results`.

```sql
CREATE TABLE ai_deep_analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    analysis_version TEXT NOT NULL,
    result_json TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    analyzed_at TEXT NOT NULL,
    UNIQUE(candidate_id, provider, model, analysis_version)
);
```

Proposed unique key:

`candidate_id + provider + model + analysis_version`

`analysis_version` identifies a prompt/schema release, for example `deep-v1`. A prompt upgrade writes a new version instead of overwriting prior analysis. Force reanalysis may update only the exact same composite key. Existing Cheap Triage results remain in their current table.

## Execution Flow

```text
Candidate selected after Cheap Triage
  -> load bounded candidate evidence and Cheap Triage result
  -> build DeepAnalysisInput
  -> enforce 2,500-character input budget
  -> check candidate/provider/model/version duplicate
  -> provider structured-output request
  -> normalize and validate DeepAnalysisResult
  -> save versioned result and usage
  -> expose result for human review
```

Failures for one candidate must not create a fabricated result or overwrite another provider/model/version result.

## Example Output

The following example uses only information already present in the Backpacking Pillow candidate: five pillows were compared; the source described differences in comfort, weight, packed size, stability, valves, straps, materials, and use cases. It does not assert supplier, MOQ, cost, sales, or market facts.

```json
{
  "candidate_id": "example-backpacking-pillow",
  "opportunity_summary": "Explore an incrementally improved backpacking pillow focused on the documented trade-offs among comfort, weight, packed size, and stability.",
  "evidence": {
    "confirmed_evidence": [
      "The source compares five backpacking pillows across comfort, weight, packed size, and use case.",
      "The source reports pain points including sliding, missing pad straps, difficult packing, insufficient height, and comfort trade-offs."
    ],
    "hypotheses": [
      "A compact pillow combining better pad stability with easier packing could be worth testing.",
      "A removable or adjustable strap may improve usability without redesigning the full product."
    ]
  },
  "customer_problem": "Users described trade-offs between sleeping comfort, stability on a pad, packed size, weight, and ease of use.",
  "existing_solution_gap": "The supplied comparison identifies separate shortcomings across products, but whether one combination is commercially differentiated requires validation.",
  "micro_innovation_ideas": [
    "Test a removable low-profile pad strap.",
    "Test a higher-friction underside material or pattern.",
    "Test a stuff-sack opening designed for easier repacking."
  ],
  "sourcing_direction": {
    "search_keywords": ["inflatable camping pillow", "backpacking pillow pad strap", "non-slip camping pillow"],
    "supplier_type": ["outdoor sewn-product manufacturer", "inflatable travel-accessory manufacturer"],
    "likely_manufacturing_category": ["outdoor sleep accessories"],
    "supplier_questions": [
      "What existing constructions and materials can be sampled?",
      "What MOQ and sample charges apply?",
      "Can strap and underside options be changed without new tooling?"
    ]
  },
  "validation_needed": [
    "supplier capability, MOQ, samples, and cost",
    "demand for the proposed feature combination",
    "competition and IP review",
    "packed shipping dimensions, margin, and durability"
  ],
  "feasibility": {
    "technical_complexity": "LOW",
    "manufacturing_complexity": "MEDIUM",
    "shipping_friendliness": "HIGH",
    "regulatory_risk": "LOW",
    "startup_cost_level": "MEDIUM"
  },
  "content_marketing_angles": [
    "Show side-by-side sliding and stability tests.",
    "Demonstrate packed size and repacking speed.",
    "Compare comfort and height for documented use cases."
  ],
  "biggest_risks": [
    "The combined feature gap may not represent sufficient demand.",
    "Durability and comfort claims require physical sample testing.",
    "Supplier, cost, competition, and IP remain unvalidated."
  ],
  "recommended_next_step": "VALIDATE_SUPPLIER",
  "deep_score": 7,
  "provider": "example",
  "model": "example",
  "analysis_version": "deep-v1",
  "analyzed_at": "example-timestamp"
}
```

The feasibility labels and score in this example are design-format illustrations, not validated product conclusions.

## Future Daily Final Opportunities

- Publish at most 10 high-quality opportunities per day.
- Physical products are the primary track.
- Software or digital opportunities are a lightweight auxiliary track and are capped at 2 per day.
- This is not a fixed 8 physical + 2 software allocation. If 10 qualified physical opportunities exist, all 10 may be physical.
- Never fill the quota with low-quality, commodity, or weak software opportunities. Fewer than 10 is acceptable.
- Physical opportunities use the Physical Deep Analysis defined here.
- Software opportunities will use a separate Lightweight Software Analysis and will not inherit 1688, manufacturing, or shipping fields.
