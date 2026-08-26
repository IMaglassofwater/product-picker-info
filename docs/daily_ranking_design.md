# Daily Opportunity Ranking Design

## Daily Report Flow (Phase 9.4)

Data Sources → Free Filters → Candidate Pool → Cheap Triage → Specificity Gate → Daily Ranking → Daily Top Opportunities → Report.

Deep Analysis is optional and on demand. A grounded stored analysis enriches scoring and report text; missing, timed-out, or ungrounded analysis falls back to Cheap Triage. An explicit Deep Analysis `DROP` or a clear existing hard risk can still exclude a candidate. Ranking weights are unchanged and no candidate is pulled in merely to fill a vacancy.

## Scoring

Each opportunity receives a transparent `final_rank_score` from 0 to 100:

| Component | Range | Source |
|---|---:|---|
| AI Opportunity Quality | 0-30 | Physical Deep Analysis or Software Analysis; otherwise Cheap Triage, then candidate fallback |
| Evidence Strength | 0-20 | Source-specific demand or market evidence already stored |
| Personal Feasibility | 0-20 | Physical feasibility score or software complexity/solo-builder fields |
| Micro-Innovation / Actionability | 0-15 | Existing analysis next step and micro-innovation signals |
| Cross-Source Confirmation | 0-10 | Same opportunity group across independent sources |
| Freshness | 0-5 | Stored record timestamp |

The engine uses a few bounded tiers rather than dozens of small magic-number adjustments. Every ranked item exposes all six components.

## Quality Gate

- Cheap Triage must be `PASS`.
- An available physical or software analysis must not recommend `DROP`.
- Existing hard-risk flags such as weapons, high regulation, complex electronics, wireless, or large/heavy goods exclude the candidate.
- The final score must reach the minimum publication threshold.
- A high relative rank never bypasses these gates.

## Physical Priority

Quality-qualified physical opportunities are considered first. This is a selection-order rule, not an artificial score bonus. Ten strong physical opportunities may occupy all ten slots.

## Software Quota

Software opportunities fill remaining slots only after physical selection and are capped at two. Zero software entries is valid. Software candidates never displace qualified physical candidates merely because Product Hunt or another software source has more records.

## Theme Diversity

Each primary theme is capped at three selected opportunities by default. A fourth bags/carry, storage, travel, or other same-theme item is excluded with `theme quota reached`, even when its score is close.

## Near Duplicate

The engine uses deterministic opportunity groups plus normalized-title token overlap. The highest-scoring representation is retained; similar records do not occupy multiple daily slots. No embeddings or AI calls are used.

## Opportunity Specificity Gate

After the existing quality gate and before final selection, physical `demand_opportunity` records pass through the free Specificity Gate. `SPECIFIC` opportunities compete normally, `REVIEW` opportunities are held for audit, and `TOO_BROAD` opportunities are excluded. Other explicit physical candidate types retain their existing eligibility, and software rules are unchanged. Specificity does not alter any ranking component or weight.

## Cross Source

Cross-source points require the same opportunity group in at least two independent sources. Multiple records from one source do not qualify. Yanko Design may provide inspiration confirmation but is capped below full market confirmation. Duplicate URLs never add confirmation.

## Fallback

Physical ranking uses a valid Physical Deep Analysis, then Gemini/available Cheap Triage, then existing candidate score. Software ranking uses valid Software Analysis, then Cheap Triage, then existing score. Missing or timed-out Deep Analysis never blocks daily publication by itself.

## Final Selection

1. Load current normalized candidates and stored evidence without network access.
2. Compute opportunity groups and independent-source confirmation.
3. Score and apply the quality gate.
4. Apply Physical demand-opportunity specificity: SPECIFIC passes, REVIEW is held, TOO_BROAD is removed.
5. Remove near duplicates.
6. Select physical opportunities first, enforcing the theme cap.
7. Fill remaining slots with at most two qualifying software opportunities.
8. Stop at ten or earlier when quality is insufficient; never force-fill.
9. Produce rule-based `selection_reason` and `exclusion_reason` strings for audit.

Daily rules remain: Top 10 maximum, Physical First, Software <=2, Theme <=3, and No Forced Fill.
