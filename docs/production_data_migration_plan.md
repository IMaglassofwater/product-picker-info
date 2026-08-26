# Production Data Migration Plan

## Principle

This is a classification audit, not a cleanup operation. The SQLite database remains unchanged. Production migration copies only reviewed production history; excluded rows stay available locally.

The skipped Product has `source_platform=Test`. It is a `TEST_ONLY` invalid development record, not a real scraped Product.

## Current Dry-Run Classification

| Data | KEEP | SKIP | Policy |
|---|---:|---:|---|
| Products | 652 | 1 | Keep six-source records; skip the single `Test` source row (`TEST_ONLY`, invalid development record) |
| Metric Snapshots | 230 | 0 | All are real Amazon, Kickstarter, or Indiegogo metric history |
| Gemini Triage | 24 | 0 | Keep provider=`gemini` |
| Mock Triage | 0 | 20 | Never migrate mock output |
| Deep Analysis | 0 | 2 | Current validation-phase v1/v2 rows are `TEST_ONLY` |
| Software Analysis | 0 | 1 | Current MVP validation row is `TEST_ONLY` |
| Specificity | 44 | 0 | Keep deterministic production screening history |
| User Feedback | 0 | 1 | Current local UI/development feedback is `TEST_ONLY` |
| Pipeline Runs | 1 | 0 | Keep the run with six real source-run records and nonzero fetches |

## Analysis Record Audit

### Deep Analysis — TEST_ONLY / DO_NOT_MIGRATE

| Candidate | Provider | Model | Version | Purpose |
|---|---|---|---|---|
| `[Comparison] I tested out and compared 5 good backpacking pillows so you don't have to.` | gemini | gemini-3.5-flash-lite | v1 | Initial single-candidate Deep Analysis validation |
| same candidate | gemini | gemini-3.5-flash-lite | v2 | Grounding/calibration validation |

### Software Analysis — TEST_ONLY / DO_NOT_MIGRATE

| Candidate | Provider | Model | Version | Purpose |
|---|---|---|---|---|
| `App that recommends smart fabric choices for one-bag travel based on destination and weather?` | gemini | gemini-3.5-flash-lite | v1 | Single software-analysis MVP validation |

Future production analyses must use an explicitly reviewed `production_*` analysis version before the current migration filter includes them.

## Pipeline and Feedback

The current pipeline run is production-relevant because it has six associated real-source rows and nonzero fetch counts. Runs without real source activity are excluded. The one existing feedback row is treated conservatively as development state and is excluded until the user explicitly reviews it.

## Command

```text
python scripts/migrate_sqlite_to_postgres.py --dry-run --production-only
```

Dry-run opens SQLite in read-only mode, prints KEEP/SKIP counts, and never connects to PostgreSQL. The separately gated `--execute --production-only` path is prepared for the user-authorized deployment stage and was not run in this phase.
