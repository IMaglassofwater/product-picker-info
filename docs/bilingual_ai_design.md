# Bilingual AI Content Foundation

## Purpose

Future Cheap Triage calls produce the English judgment and its grounded Simplified Chinese presentation in one structured response. This avoids a second translation request and keeps both languages tied to one evidence set.

## Cheap Triage Fields

Existing English and decision fields remain unchanged:

- `triage_status`, `triage_score`, `confidence`, `opportunity_type`
- `primary_reason`, `key_opportunity`, `main_risks`
- `needs_deep_analysis`

New bilingual presentation fields:

- `display_title_zh` — nullable when a faithful concise title is not possible
- `primary_reason_zh`
- `key_opportunity_zh`
- `main_risks_zh` — at most three compact risks

The original source title is never modified.

## Grounding

Chinese fields must express the same facts and uncertainty as English. They cannot introduce supplier availability, MOQ, costs, market size, competition, customer profiles, certification, regulation, IP status, or other claims absent from the input and English judgment.

## Database Compatibility

`ai_triage_results` uses nullable text columns for the first three Chinese text fields and JSON text for `main_risks_zh`. Initialization adds missing columns with `ALTER TABLE`; it does not rebuild the database, alter the `(candidate_id, provider, model)` uniqueness rule, or overwrite Mock/Gemini history. Old rows load with `None`/empty Chinese values.

## Display Priority

1. Persisted AI `display_title_zh`
2. Existing deterministic title mapping
3. Original English title

For AI body content, persisted Chinese is displayed first. Missing Chinese uses the compact `待补充` marker followed immediately by the complete English field. All Products does not require every historical product to have a translation.

## Historical Backfill

`bilingual_backfill.py` selects only candidates that already have a real Gemini result for `gemini-3.5-flash-lite` and are missing one or more Chinese fields. Its merge function can update only bilingual fields; status, score, confidence, English judgment, and model identity are preserved.

Backfill is intended as translation-only/bilingual enrichment. No batch backfill runs in Phase 9.7B. Current eligible historical results: 24.

## Future Analysis Fields

Software Analysis may later add `opportunity_summary_zh`, `user_problem_zh`, `mvp_idea_zh`, and `biggest_risks_zh`. Deep Analysis bilingual output remains deferred until a user requests deeper research.
