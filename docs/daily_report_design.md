# Daily Report Foundation

## Purpose

The Daily Report is a compact Opportunity Feed of at most ten current candidates. It is not a full business plan and makes no network or AI calls during generation.

Phase 9.5 extends this into a bilingual Full Qualified Opportunity Feed. Top Picks remain capped at ten, while all core-qualified records remain visible in the categorized feed.

## Eligibility and Ordering

The report consumes two views of the same scored candidates. Top Picks retain Physical First, Software ≤2, Theme ≤3, Top 10 maximum, and No Forced Fill. Full Feed retains Cheap Triage PASS, Specificity and hard-risk gates, but does not hide records solely because of final score, theme quota, software quota, or Top 10 position.

## Analysis Priority

- Physical: valid grounded Physical Deep Analysis, then Cheap Triage.
- Software: valid Software Analysis, then Cheap Triage.
- Missing or timed-out Deep Analysis: Cheap Triage fallback.
- Ungrounded Deep Analysis: excluded as report evidence and shown internally as `DEEP_ANALYSIS_FAILED`.
- Explicit Deep Analysis `DROP` or an existing hard risk may still exclude the candidate.

## Data Structure

`DailyReportItem` contains rank, candidate ID, display title, candidate and opportunity types, source, theme, final score, triage score, compact reason, key opportunity, risks, research status, source URL, and optional deep score/next step.

Research statuses are `TRIAGED`, `DEEP_ANALYZED`, and `DEEP_ANALYSIS_FAILED`. The user-visible label for the last state is “可进一步深挖”.

## HTML

The report is written to `reports/YYYY-MM-DD-product-picker.html`. It uses standalone semantic HTML and inline CSS, with no JavaScript, CDN, external fonts, raw data, credentials, or API keys.

Cards preserve English source text and add conservative Chinese rule summaries without introducing facts absent from the record. Fixed interface labels are bilingual. Source links open in a new tab with `noopener noreferrer`.

## On-Demand Research

Deep Analysis remains available after the user expresses interest in an opportunity, for supplier, competition, 1688, cost/MOQ, micro-innovation, and marketing validation work.
