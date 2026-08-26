# Final Opportunity Specificity Gate

## Purpose

The free Specificity Gate asks whether a physical opportunity is concrete enough to justify Deep Analysis. It does not re-evaluate demand truth, manufacturability, market size, or feasibility.

## Output

- `specificity_status`: `SPECIFIC`, `REVIEW`, or `TOO_BROAD`
- `specificity_score`: 0-100
- `specificity_reason`: concise rule-generated explanation
- `specificity_flags`: transparent detected signals

## SPECIFIC

A specific demand opportunity identifies one base product family, an explicit problem or requirement, and at least one researchable improvement direction. Examples include a zipperless fanny pack, a key organizer for defined key shapes/counts, a price-driven DIY journal alternative, or a camping pillow with documented comfort and packed-size trade-offs.

## REVIEW

The product family or use case is partly identifiable, but the requested feature gap is incomplete or multiple products could solve the need. REVIEW items remain audit candidates and are not selected into the daily final list by default.

## TOO_BROAD

General advice, trip planning, packing-list review, unspecified EDC suggestions, setup optimization, or generic recommendations are too broad when the current evidence does not identify one product family plus a specific problem or feature gap.

## Signals

Positive signals include explicit product, feature, size, material, opening, storage, use-case, price, ergonomic, portability, appearance, DIY, and existing-product evidence. Broad signals include packing advice, setup optimization, multi-product requests, trip planning, gear-list review, unspecified EDC requests, and generic alternatives.

No single keyword determines the result. The rule combines title, bounded description, and existing candidate signals.

## Candidate Types

The gate primarily controls physical `demand_opportunity` candidates. Explicit products from `validated_product`, `consumer_trend`, and `inspiration_product` are protected from being rejected merely because their source is not a Reddit pain-point post. Software selection is unchanged.

## Daily Integration

The gate runs after the existing Cheap Triage/hard-risk quality gate and before near-duplicate, theme-quota, and final-slot selection:

```text
existing quality gate
  -> Physical demand specificity
     -> SPECIFIC: compete normally
     -> REVIEW: hold for audit
     -> TOO_BROAD: remove from daily final
  -> near duplicate
  -> Physical First / Theme <=3 / Software <=2
  -> Top 10 maximum, no forced fill
```

Specificity is not added to `final_rank_score`; all six Phase 9.1 score weights remain unchanged.
