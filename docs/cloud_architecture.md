# Product Picker Cloud Architecture

## Runtime Separation

```text
Private GitHub repository
  ├─ Web service: streamlit run app.py
  │    └─ read/query + user feedback only
  └─ GitHub Actions scheduled worker: python run_daily.py
       ├─ six public-source scrapers
       ├─ persistence and offline filters
       ├─ candidate construction
       ├─ Gemini Cheap Triage (degradable)
       └─ specificity and ranking

Neon PostgreSQL
  └─ products, history, AI results, runs, feedback
```

`app.py` never imports scraper modules or runs ingestion. `run_daily.py` never imports Streamlit. The first cloud deployment should use one web process and one scheduler process against one durable PostgreSQL database.

## Runtime Status and Degradation

Pipeline status is `SUCCESS`, `PARTIAL`, or `FAILED`. Source or Gemini failures never invent data. Fetched products remain durable. When Gemini is unavailable, missing results remain `AI Pending`, the run finishes `PARTIAL`, and later runs may continue coverage. Database/initialization failure is `FAILED`.

The local file lock prevents overlapping single-instance runs. Before horizontally scaling workers, PostgreSQL should replace it with an advisory lock.

## Configuration and Time

`DATABASE_URL` selects the backend. When unset, the app uses `data/product_picker.db`; `postgres://` and `postgresql://` use the pooled psycopg PostgreSQL implementation. Streamlit receives only `DATABASE_URL`; GitHub Actions receives `DATABASE_URL` and `GEMINI_API_KEY`.

Database timestamps are UTC. Business reporting and Web display use `Asia/Tokyo`. No production schedule is selected in this phase.

## Bilingual Degradation

Persisted Chinese is shown first with English comparison. When Chinese is missing, English is primary and the card shows one compact `中文待补充 · Chinese pending` marker.
