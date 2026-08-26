# Product Picker Web App MVP Design

## Purpose

Phase 9.7 provides a local, bilingual Streamlit interface over the existing SQLite data. It does not scrape sources or call AI providers.

## Structure

- `app.py`: navigation, filters, cards, details, pagination, and feedback controls.
- `dashboard_data.py`: bounded SQLite snapshot queries, normalized display records, filtering, feedback, and re-evaluation actions.
- `data/product_picker.db`: the single runtime database.

The data layer loads products, candidates, Gemini results, analysis summaries, specificity, metric history, feedback, the latest pipeline run, and the re-evaluation queue in a fixed number of queries. Product cards do not open one database connection per card. Streamlit caches the snapshot for 30 seconds; successful writes clear the cache immediately. The dashboard never imports scrapers or starts the daily pipeline.

## Pages

1. 今日机会 · Today: current Top Picks, full qualified feed, AI Pending count, and latest source-run status.
2. 全部产品 · All Products: all stored products, filters, pagination, details, and actions.
3. 软件机会 · Software: all software records without the Top Picks software quota.
4. 我的收藏 · Favorites: records with `FAVORITE` status.
5. 观察列表 · Watchlist: records with `WATCH` status and metric history in details.
6. 淘汰库 · Rejected / Archive: rejected/review/commodity/too-broad records and the re-evaluation queue.

## State and Safety

`FAVORITE`, `WATCH`, and `NOT_INTERESTED` are mutually exclusive because the database uses one feedback row per entity. `RE_EVALUATE` is stored independently as a pending request and never calls AI in this phase. Missing Gemini results display as `AI_PENDING`; they remain searchable and actionable.

The UI does not expose `.env`, API keys, prompts, the database path, authorization data, or full `raw_data`. Only allow-listed analysis summaries and metric snapshots are shown.

## Compatibility

Legacy records with an empty or NULL description normalize to an empty string. They remain visible without changing their stored source data. Current verification loads all 653 database rows.

## Bilingual Display Compatibility

The six primary pages are always visible as top navigation tabs. Fixed UI labels, filters, statuses, source/type labels, feedback actions, and empty states are Chinese-first with English comparison text. Known deterministic title mappings are reused. Existing dynamic English AI fields remain intact; where no reliable Chinese content exists, the UI shows the compact `待补充` marker and immediately preserves the English text instead of inventing a translation.

When persisted Chinese is missing, English becomes the main content and only one compact `中文待补充 · Chinese pending` marker is shown. Existing English is never hidden or replaced by an invented translation.

## Product Information Layer

Cards now separate Product Information, Source Evidence, and AI Opportunity Analysis. Product summaries are deterministic projections of stored descriptions or allow-listed source metadata, so all 653 records remain readable without Gemini. Products without a Candidate are `NOT_ANALYZED`; Candidate records awaiting a real result are `AI_PENDING`.

Metadata, summaries, and AI analysis use complete English blocks followed by complete Chinese blocks. All Products keeps AI details in an expander, while Today displays Product Summary and available AI analysis. English-only AI results receive one pending label and never a generic Chinese judgment template. Full raw source dictionaries are never rendered.
