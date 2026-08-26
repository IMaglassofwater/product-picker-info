# Final Deep Gate Design

## Purpose and Optional Status

Deep Analysis is optional for the daily report. The Final Deep Gate remains an offline, deterministic check when a stored analysis exists or when a strict, explicitly requested finalist audit is run.

## Position in the Flow

Daily default: Cheap Triage → Specificity Gate → Daily Ranking → Report, with optional stored Deep Analysis enrichment.

Strict audit mode: Ranking Finalist → Physical Deep Analysis v2 → Final Deep Gate.

## Decisions

- `PASS`: `deep_score >= 6`, no `DROP` recommendation, no detected unsupported claim, no explicit insufficient-product-gap finding, and no HIGH regulatory or engineering/manufacturing barrier.
- `REVIEW`: `deep_score` 4–5, an explicit insufficient product gap, HIGH regulatory risk, or HIGH engineering/manufacturing barrier.
- `DROP`: `recommended_next_step = DROP` or `deep_score <= 3`.
- `HUMAN_REVIEW`: deterministic grounding checks detect unsupported claims.
- In strict audit mode, `analysis_failed` is held and Cheap Triage cannot substitute.
- In daily mode, missing/timeout analysis falls back to Cheap Triage and does not block publication.
- In daily mode, an ungrounded stored analysis is not used as report evidence; the candidate falls back to grounded Cheap Triage.
- An explicit `recommended_next_step = DROP` or an existing clear hard risk still excludes the candidate.

## Grounding

The gate reuses the finalized unsupported-claim checks for supplier, MOQ/cost, market, competition, certification, patent, margin, and demand assertions. It does not call AI.

## Ranking Invariants

Phase 9.1 component weights remain unchanged. Valid Physical Deep Analysis takes priority over Cheap Triage when present. Top 10 maximum, Physical First, Software ≤2, Theme ≤3, Specificity Gate, and No Forced Fill remain active.

## Future On-Demand Use

After the user selects an opportunity, Deep Analysis may support supplier research, competition research, 1688 validation, cost/MOQ validation, micro-innovation expansion, and marketing research. It is not required for all daily candidates.
