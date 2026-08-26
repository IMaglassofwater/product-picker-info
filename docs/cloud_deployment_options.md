# Cloud Deployment Options

Capabilities and prices change; recheck official documentation and current pricing immediately before deployment.

| Option | Web | Scheduler | PostgreSQL | Secrets | Low-cost / stability notes |
|---|---|---|---|---|---|
| Render | Web Service | Cron Job / Background Worker | Managed Render Postgres | Environment secrets | Free services can sleep; free PostgreSQL is temporary, so durable data needs a suitable paid tier (recheck). Cron prevents overlapping runs. |
| Railway | Service | Service cron schedule | PostgreSQL service | Project/service variables | Integrated workflow; recheck current usage allowance, retention, backups, and scheduler constraints. |
| Streamlit Community Cloud + external PostgreSQL | Native Streamlit | Requires a separate scheduler/worker provider | External | Streamlit secrets | Free UI hosting and app hibernation; split providers add operational complexity. |

## Recommendation

**Render — recommended for first integrated deployment, pending price/retention review.** It separates a Streamlit Web Service from a Cron Job and offers managed PostgreSQL and secrets. The cron single-run behavior directly supports the no-overlap requirement.

## Phase 9.8B Zero-Cost Selection

For the user's explicitly selected near-zero-cost package, the implementation target is now **Streamlit Community Cloud + GitHub Actions + Neon PostgreSQL**. This trades the operational simplicity of Render for separate free-tier services. Current allowances, private-repository Actions minutes, database storage, sleep behavior, and service terms must be rechecked before enabling the daily schedule.

Official references:

- [Render service types](https://render.com/docs/service-types)
- [Render cron jobs](https://render.com/docs/cronjobs)
- [Render deploy/filesystem behavior](https://render.com/docs/deploys)
- [Railway cron jobs](https://docs.railway.com/reference/cron-jobs)
- [Railway PostgreSQL](https://docs.railway.com/guides/postgresql)
- [Railway variables](https://docs.railway.com/guides/variables)
- [Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud)
- [Streamlit secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
- [Streamlit PostgreSQL](https://docs.streamlit.io/develop/tutorials/databases/postgresql)
