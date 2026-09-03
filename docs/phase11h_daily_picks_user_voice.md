# Phase 11H — Daily Picks and Real User Voice

## Daily Picks

Daily Picks is a persisted deterministic projection of the complete Daily Discovery snapshot. It uses source-native evidence, engagement, freshness, family uniqueness, soft source caps, and bounded exploration. It does not use Gemini, Candidate status, Qualified status, Final Score, or any business-opportunity verdict.

The complete Daily Discovery membership remains unchanged and separately browseable.

## User Voice source audit

| Source | Actual user-written text currently stored | Current retrieval status |
|---|---:|---|
| Amazon | No | Aggregate rating/review count only; no compliant text transport in this project |
| Kickstarter | No | Public campaign metadata only |
| Indiegogo | No | Official public API provides counts, not discussion text |
| Reddit | Yes | Public post text with Reddit permalink through Arctic Shift |
| Product Hunt | No | RSS/public metadata does not expose stable comment text |
| Hacker News | Yes when fetched | Official Firebase item/comment API is public and stable |
| Software Reddit | Yes | Public post text with Reddit permalink through Arctic Shift |
| Yanko Design | No | Editorial text is not user feedback |

Only explicit review/comment fields and public user-authored Reddit/Hacker News text enter `user_voice_items`. Ratings, votes, backers, descriptions, and marketing copy cannot generate likes or complaints. Unclassified user text is shown conservatively as “其他讨论” with its source URL.

## Current preview

The current production snapshot contains 182 Daily Discovery families. The deterministic preview selected 15 Daily Picks, within the accepted 15–25 range. Preview artifacts are generated under ignored `.phase11h-preview/`; no live WxPusher message is sent and the production UI flag remains disabled.
