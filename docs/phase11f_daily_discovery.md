# Phase 11F Daily Discovery Product Experience

## Single source of truth

`daily_discovery_runs` and `daily_discovery_items` persist a run-scoped, ordered snapshot. Membership is based on an explicit observation in the selected pipeline run plus `ELIGIBLE`, `CONCRETE`, and an active Product Family. Historical favorites are not automatically included.

The authoritative order is evidence strength (`STRONG`, `MODERATE`, `WEAK`), observation freshness, normalized name, and family ID. `display_order` is persisted and neither renderer changes it.

## Renderers

The Evidence-First Today renderer and complete WxPusher renderer consume the exact persisted `items` list. The WxPusher renderer uses conservative 20-item chunks for compact delivery; this is an application choice, not a claimed WxPusher service limit. Every family ID is retained in order.

The Today UI is Chinese-first and keeps English originals in secondary details. Its filters and family-level `HIDDEN`/`DISMISSED` feedback only change the interactive view, never the historical snapshot. `FAVORITE` also leaves membership unchanged.

## Evidence and AI boundary

Cards show source-native evidence instead of a cross-source opportunity score. Likes/dislikes are only shown when source text exists in an explicitly recognized feedback field, together with source provenance. Otherwise the UI says that no user text feedback is available.

AI is not a visibility gate. Missing translation falls back to factual source text and cannot remove a qualifying family. No business verdict, final score, invented demand, supplier, cost, or feedback is generated here.

## Cutover status

The new Today page is guarded by `EVIDENCE_FIRST_TODAY_ENABLED=false`. The complete WxPusher renderer is prepared but is not connected to live sending. Production UI and notification behavior remain unchanged pending user review.

Deferred sources remain Etsy (`DEFERRED_PENDING_PERSONAL_APPROVAL`) and Design Milk (`DEFERRED`). GitHub, Core77, and Designboom were not added.
