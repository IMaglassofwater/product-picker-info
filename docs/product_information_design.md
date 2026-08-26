# Product Information Design

## Core Separation

`Product Information != AI Opportunity Analysis`.

Every stored product remains understandable without a Candidate or AI result. The UI has three distinct layers:

1. Product Information answers “What is it?” from stored source text.
2. Source Evidence shows only allow-listed public metadata supplied by the source.
3. AI Opportunity Analysis answers whether further research may be worthwhile, only when a real AI result exists.

## Product Summary

The deterministic display helper selects `description`, then a public tagline/excerpt/description field in stored source metadata, then the title. It only strips markup, normalizes whitespace, and safely truncates. It does not rewrite claims or call AI. If no text exists, it displays `Description not available.` / `产品简介暂无。`.

## AI State

- `NOT_ANALYZED`: the Product has not entered the Candidate AI analysis path.
- `AI_PENDING`: the Product has a Candidate identity but no current Gemini result.
- A real triage status (`PASS`, `REVIEW`, `REJECT`) is shown only for persisted output.

Missing AI never creates empty Why It Matters, Opportunity, and Main Risks sections.

## Bilingual Layout

The layout is an English grouped block followed by a Chinese grouped block. Titles and action buttons remain compact bilingual controls. If a whole Chinese region is absent, the region gets one small pending label—title, summary, or analysis—rather than repeated placeholders.

Today cards show Product Summary plus AI analysis when present. Only persisted `*_zh` AI fields count as real Chinese analysis; English-only historical results show one Chinese-analysis-pending label. All Products cards prioritize title, grouped metadata, summary, AI state, and feedback; detailed analysis and screening history live in expanders.

## Source Evidence

The display layer allow-lists Reddit community/interaction data, Amazon price/rating/reviews/rank, Kickstarter and Indiegogo funding data, Product Hunt tagline/topics/votes, and Yanko category/excerpt/publication date. Missing fields stay absent. Raw dictionaries, raw HTML, credentials, and arbitrary JSON are never rendered.
