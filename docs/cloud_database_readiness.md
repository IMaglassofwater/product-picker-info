# Cloud Database Readiness

## Status

**PARTIAL** — the logical data model is ready for a planned PostgreSQL migration, but no migration or cloud deployment is performed in Phase 9.5B.

## Tables That Map Directly

- `products`
- `processed_projects`
- `micro_innovation_candidates`
- `ai_triage_results`
- `deep_analysis_results`
- `software_analysis_results`
- `product_metric_snapshots`
- `pipeline_runs`
- `pipeline_source_runs`
- `specificity_results`
- `user_product_feedback`
- `re_evaluation_requests`

Primary keys and composite uniqueness constraints have clear PostgreSQL equivalents. New run/snapshot tables use explicit foreign keys where the current identity is stable.

## Required Conversions

1. Convert SQLite `INTEGER PRIMARY KEY AUTOINCREMENT` to PostgreSQL identity/bigserial columns.
2. Convert timestamp TEXT values to `TIMESTAMPTZ` after normalizing legacy SQLite `CURRENT_TIMESTAMP` strings and ISO-8601 strings.
3. Convert serialized JSON TEXT (`raw_data`, flags, result JSON, metric_data) to `JSONB`, with validation before import.
4. Convert integer booleans such as `failed` and `needs_deep_analysis` to PostgreSQL BOOLEAN.
5. Enable and validate all foreign keys; legacy AI/candidate rows currently rely partly on logical IDs rather than enforced candidate foreign keys.

## Remaining Risks

- Product identity is URL-based. Canonical URL changes can create a second logical Product.
- Candidate replacement operations need explicit archival semantics before multi-user/cloud operation.
- Mixed legacy timestamp formats require one migration normalization pass.
- JSON structures are source-specific and need versioned validation for analytics.
- Concurrent writers will require transactions/locking semantics beyond the current single-process SQLite assumptions.

## Recommended Migration Order

1. Freeze writes and back up SQLite.
2. Create PostgreSQL schema with typed timestamps, booleans, and JSONB.
3. Import base Products, then candidates, AI results, snapshots, runs, specificity, and feedback.
4. Verify row counts, uniqueness, foreign keys, and sampled JSON equivalence.
5. Switch through a persistence abstraction only after parity tests pass.
