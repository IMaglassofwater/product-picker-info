# Configure GitHub Actions

Do this only after Neon migration and Streamlit read/write smoke checks succeed.

1. Open the private repository.
2. Go to **Settings → Secrets and variables → Actions**.
3. Add repository secret `DATABASE_URL` with the same pooled Neon connection string.
4. Add repository secret `GEMINI_API_KEY`.
5. Open **Actions → Daily Product Picker → Run workflow** for the first controlled run.
6. Confirm `pipeline_runs`, each source status, new Products, and AI Pending behavior in the Web app.
7. Only after this manual check, add repository variable `DAILY_SCHEDULE_ENABLED=true`. Scheduled events are ignored until this variable exists.

The workflow has no push trigger. Its cron is `0 23 * * *`: 23:00 UTC, which is 08:00 Asia/Tokyo on the following date. `workflow_dispatch` allows a manual run. The schedule is guarded by `DAILY_SCHEDULE_ENABLED`. `PARTIAL` (including Gemini degradation) exits successfully; database failure or all-source failure exits nonzero.

## Required first-deployment order

1. Create Neon.
2. Initialize schema.
3. Run migration dry run.
4. Run production-only migration.
5. Verify counts.
6. Connect Streamlit.
7. Run Web app smoke test.
8. Manually dispatch GitHub Actions.
9. Check new data.
10. Only then leave the daily schedule active.

GitHub Actions plan allowances and private-repository minutes may change; check the current official billing documentation before enabling the schedule.
