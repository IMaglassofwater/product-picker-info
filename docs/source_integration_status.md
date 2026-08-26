# Source Integration Status

Updated: 2026-08-26 after Phase 9.5B six-source production validation.

| Source | Scraper | Default main pipeline | Normal run | Access method | Authentication | Products | Candidate table | Status |
|---|---|---|---|---|---|---:|---:|---|
| Reddit / Arctic Shift | YES | YES | YES | Third-party Arctic Shift public JSON API | NO | 261 | 40 | PRODUCTION |
| Amazon | YES | YES | YES | Public Movers/New Releases HTML | NO | 35 | 1 | PRODUCTION |
| Product Hunt | YES | YES | YES | Public RSS plus public page metadata | NO | 136 | 0 | PRODUCTION |
| Yanko Design | YES | YES | YES | Public RSS | NO | 20 | 3 | PRODUCTION |
| Kickstarter / KSInsights | YES | YES | YES | Third-party public KSInsights CSV via GitHub API | NO | 100 | 0 | PRODUCTION |
| Indiegogo | YES | YES | YES | Official public active-projects JSON API | NO | 100 | 0 | PRODUCTION |
| Designboom | NO | NO | NO | RSS/HTML access was probed only | NO | 0 | 0 | PROBE_ONLY |
| Etsy | NO | NO | NO | No data access implementation; credential placeholders only | YES for planned official integration | 0 | 0 | PARTIAL / NOT_IN_PIPELINE |

## Default Registry

`main.py` now defines six default sources: Product Hunt, Kickstarter/KSInsights, Reddit/Arctic Shift, Amazon, Yanko Design, and Indiegogo. Each fetch is independently contained; a failed source is written to `pipeline_source_runs` and does not stop later sources. The legacy Reddit RSS scraper remains available, while the default registry uses Arctic Shift.

## Important Source Notes

- Arctic Shift is explicitly documented in code as a third-party historical Reddit service, not Reddit's official API.
- Kickstarter does not access Kickstarter pages directly; it consumes the public third-party KSInsights dataset.
- Indiegogo now uses the probed official public `getActiveCrowdfundingProjects` endpoint without authentication. The first production run fetched and saved 100 projects without fabricating unavailable fields.
- Designboom has probe evidence only and no scraper.
- Etsy has configuration readiness (`ETSY_API_KEY`, shared secret checks) but no scraper, pipeline integration, or records.

## Phase 9.5B Production Run

| Source | Fetched | Saved new | Updated/seen again | Failed | Rejected | New candidates | Error |
|---|---:|---:|---:|---:|---:|---:|---|
| Product Hunt | 50 | 25 | 25 | 0 | 0 | 0 | |
| Kickstarter / KSInsights | 555 (100 processed) | 0 | 100 | 0 | 9 | 0 | |
| Reddit / Arctic Shift | 30 | 29 | 1 | 0 | 6 | 9 | |
| Amazon | 30 | 5 | 25 | 0 | 0 | 0 | |
| Yanko Design | 10 | 10 | 0 | 0 | 0 | 2 | |
| Indiegogo | 100 | 100 | 0 | 0 | 4 | 0 | |

## Candidate Count Caveat

“Candidate table” means rows currently present in `micro_innovation_candidates`. Software-like product records may exist in `products` without a candidate-table row. Candidate types can also be replaced by `replace_candidates_by_type`, so this table is a current pool rather than a complete immutable candidate history.
