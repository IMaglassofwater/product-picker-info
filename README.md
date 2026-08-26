# Product Picker

An overseas multi-source product discovery and AI-assisted micro-innovation product selection system.

Current development stage: Phase 0 - Project initialization

## Run

```bash
python main.py
```

## Cloud deployment package

The prepared zero-cost-oriented architecture uses a private GitHub repository, GitHub Actions for the daily job, Neon PostgreSQL for durable shared data, and Streamlit Community Cloud for `app.py`. Local development continues to use SQLite when `DATABASE_URL` is unset.

Deployment is intentionally manual. Follow `docs/deploy_neon.md`, `docs/deploy_streamlit_cloud.md`, and `docs/deploy_github_actions.md`. Never commit `.env`, database files, API keys, or PostgreSQL connection strings.
