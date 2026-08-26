# Deploy Neon PostgreSQL

No account or database was created during Phase 9.8B. Recheck the current Neon plan limits before deployment; Neon documents scale-to-zero behavior for intermittent workloads.

1. Create a Neon account and a new project.
2. Copy the pooled PostgreSQL connection string and store it in a password manager. Never add it to Git or `.env.example`.
3. Locally set `POSTGRES_DATABASE_URL` only for the approved migration session.
4. Run `python scripts/migrate_sqlite_to_postgres.py --dry-run --production-only`.
5. After reviewing its exact KEEP/SKIP list, explicitly run `--execute --production-only` to initialize schema and copy reviewed records.
6. Verify Neon counts against SQLite: Products 652, Metric Snapshots 230, Gemini Triage 24, Specificity 44, plus the classified production run records.
7. If any count is lower, stop before connecting the Web app or scheduler.
8. Save the Neon string as GitHub Actions secret `DATABASE_URL` and as the only Streamlit app secret `DATABASE_URL`.

The one skipped Product has `source_platform=Test`; it is an invalid development record, remains in local SQLite, and is never silently deleted.

Reference: [Neon scale to zero](https://neon.com/docs/introduction/scale-to-zero).
