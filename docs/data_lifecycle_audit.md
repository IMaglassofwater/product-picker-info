# Product Picker Data Lifecycle Audit

Audit date: 2026-08-26. SQLite was opened read-only. No network or AI call was made.

## 1. Actual Data Flow

The normal pipeline is:

1. `scraper.fetch()` returns normalized `Product` objects in memory.
2. Rule, role, feasibility, demand-signal, and demand-opportunity filters run in memory.
3. `save_products(...)` inserts **all processed fetched products**, including rejected and review records, together with the computed rule fields.
4. Candidate builders accept only qualifying results and `save_candidates(...)` inserts the current candidate pool.
5. Gemini Triage is not part of the default `python main.py` pipeline. Explicit validation/batch paths save provider results later to `ai_triage_results`.
6. Specificity and Daily Ranking are calculated downstream from stored products/candidates/Triage results.

Database save timing is therefore **AFTER_FILTER**. The important preservation property is that filter rejection does not prevent the processed Product from being inserted.

## 2. Rejected and Review Preservation

| Decision | Stored | Stored in | Reason preserved | Re-evaluable |
|---|---|---|---|---|
| Rule Filter `rejected` | YES | `products` | YES: `filter_reason` | YES |
| Feasibility `REJECT` | YES | `products` | YES: `feasibility_reason`, `risk_flags` | YES |
| Commodity `COMMODITY` | YES | `products` | YES: `commodity_reason`, `commodity_flags` | YES |
| Specificity `TOO_BROAD` | PARTIAL | Underlying `products`/candidate may exist; decision is not persisted | NO persisted specificity status/reason | YES, by recomputing current rules |
| Gemini Triage `REVIEW` | YES | `ai_triage_results` | YES: primary reason, opportunity, risks | YES |
| Gemini Triage `REJECT` | YES | `ai_triage_results` | YES | YES |

Candidate creation is selective, so a rejected Product usually has no candidate row. This does not delete the Product record.

## 3. Database Inventory

| Table | Rows | Purpose |
|---|---:|---|
| `products` | 484 | Normalized fetched record, raw JSON, and free-filter results |
| `micro_innovation_candidates` | 33 | Current qualified candidate pool |
| `ai_triage_results` | 44 | Provider/model-specific Cheap Triage history |
| `deep_analysis_results` | 2 | Versioned Physical Deep Analysis results |
| `software_analysis_results` | 1 | Versioned Software Analysis results |
| `processed_projects` | 1 | URL-based processed/pushed marker |

## 4. Current Status Inventory

- Products: 484
- Rule `candidate`: 94
- Rule `rejected`: 20
- Rule `uncertain`: 330; blank legacy/unclassified: 40
- Feasibility `REVIEW`: 83; `REJECT`: 43; `PASS`: 5; blank/not applicable: 353
- Commodity `COMMODITY`: 3; `REVIEW`: 3; `PROMISING`: 1; blank/not applicable: 477
- Software opportunity type: 42; software record role: 31. These differ because the fields represent different classification stages.
- Demand Signal records: 120 (`HIGH` 42, `MEDIUM` 67, `LOW` 11)
- Demand Opportunity: `PRODUCTIZABLE` 26, `REVIEW` 70, `NOT_FIT` 11
- All stored Triage: PASS 21, REVIEW 14, REJECT 9 (Gemini: PASS 15, REVIEW 3, REJECT 6; Mock: 20 total)

There is no single universal “Review” column; review states belong to separate filter stages and must be queried independently.

## 5. History and Timestamps

Present timestamp fields:

- `products.created_at`
- `micro_innovation_candidates.created_at`
- `processed_projects.pushed_at`
- `ai_triage_results.analyzed_at`
- deep/software analysis `created_at`, `updated_at`

Absent from products/candidates: `updated_at`, `first_seen_at`, `last_seen_at`. There is no ingestion-run table or product-version/history table.

Product dates:

- Earliest: 2026-08-20 06:01:13
- Latest: 2026-08-25 10:16:34
- 2026-08-20: 51
- 2026-08-22: 19
- 2026-08-25: 414

Old unique URLs remain in `products`, so older records are present. This is not full historical versioning.

## 6. Deduplication

- Product persistence key: `products.url UNIQUE`.
- `save_products` uses `INSERT OR IGNORE`; duplicate URLs increment the duplicate count.
- For duplicates with new filter results, only filter/result columns are updated. Title, description, raw_data, source fields, and `created_at` are not updated.
- Candidate in-memory deduplication: highest candidate score per `source_url`.
- Candidate persistence: both `candidate_id UNIQUE` and `source_url UNIQUE`; candidate ID is derived from candidate type plus URL.
- Triage key: `(candidate_id, provider, model)`.
- Deep/software analysis key: `(candidate_id, provider, model, analysis_version)`.
- Daily reporting performs later opportunity-group/title similarity control for Top Picks.

If the same URL is fetched tomorrow, no second Product row is inserted. Its filter fields may be refreshed, but raw metadata and `created_at` remain from the first insert. If Kickstarter funding changes at the same URL, the new funding values in `raw_data` are ignored and no historical snapshot is created.

## 7. Current vs Target Lifecycle

Target:

Fetched valid record → raw/products persistence → dedup/version observation → free filters with every decision preserved → candidate pool → every Gemini outcome preserved → ranking/report.

Current strengths:

- Processed fetched Products are retained even when free rules reject them.
- Most free-filter reasons and all Triage outcomes are queryable.
- Provider/model/version uniqueness prevents unrelated AI results from overwriting each other.

Main gaps:

1. Persistence happens after filter execution rather than first creating an immutable raw observation.
2. URL dedup has no first/last-seen tracking and no changing-metadata snapshots; Kickstarter/Amazon metrics cannot be trended.
3. Specificity/report decisions are not persisted, candidate replacement can remove current candidate rows, and no pipeline-run lineage connects a record to each evaluation version.
4. No user-curation state or unified lifecycle-status history exists.

## 8. Phase 9.5B Upgrade

Phase 9.5B closes the principal storage gaps while retaining all legacy records:

- `products.first_seen_at`, `last_seen_at`, and `updated_at` were added safely. Existing rows use `created_at` as the explicit migration fallback.
- Duplicate URLs now retain `first_seen_at`, refresh `last_seen_at`/`updated_at`, and update current title, description, category, image, and raw_data.
- `product_metric_snapshots` stores only non-empty source metrics and adds a snapshot only when the normalized metric JSON changes. Kickstarter/Indiegogo funding/backers/status and Amazon rank/rating/reviews/price are supported when actually present.
- `pipeline_runs` and `pipeline_source_runs` persist run/source health and counts.
- `specificity_results` persists SPECIFIC/REVIEW/TOO_BROAD with score, reason, flags, rule version, and evaluation time. All 44 current candidates were backfilled for v1.
- `user_product_feedback` stores one current FAVORITE/WATCH/NOT_INTERESTED state per product or candidate. `re_evaluation_requests` stores RE_EVALUATE as a separate action queue.
- Rejected Products, software records, Triage results, and analysis history remain intact.

The database now has observation history for dynamic metrics, but it still does not store immutable full Product payload snapshots for every fetch. This is intentional: unchanged metrics do not create redundant rows.
