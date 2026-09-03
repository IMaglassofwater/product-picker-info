# Phase 11I-A Production Integration

## Architecture

`daily_picks_runs` and `daily_picks_items.snapshot_json` remain the single historical Daily Picks dataset. The snapshot contains the selected Product Directions, order, representative families, evidence, User Voice, translations, originals, and source links. Streamlit and WxPusher consume this persisted dataset; neither selects an independent list.

`product_directions` stores stable deterministic direction identities. `product_direction_members` preserves the direction-to-family relationship without replacing Product Family. User Voice remains deduplicated by `identity_key` and gains additive provenance and translation fields.

## Additive migration

The PostgreSQL schema initializer adds the two direction tables, notification delivery ledger, nullable Daily direction reference, and nullable/defaulted User Voice fields. It contains no `DROP`, `TRUNCATE`, product deletion, family deletion, or feedback rewrite. Re-running it is idempotent through `CREATE TABLE IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS`.

No production migration is executed by Phase 11I-A. Before deployment, run the normal additive schema deployment in dry-run/review mode, verify row-count expectations, then execute it once through the approved production migration workflow.

## Bounded approved-data backfill

`python scripts/phase11i_prepare.py --dry-run` loads the manually approved Phase 11H snapshot, adds stable render identities, persists it into a temporary SQLite database, reloads it, simulates changes to underlying direction rows, and verifies historical output remains unchanged. It writes preview artifacts only under the ignored `.phase11i-preview/` directory.

The production backfill must use the same current persisted Daily Discovery run, build Product Directions without external scraping, persist one Daily Picks snapshot, and verify Web/WxPusher parity before notification is enabled. It must not delete Products, Product Families, evidence, Favorites, or existing User Voice.

## Notification safety

Full-fidelity messages split only between Product Directions. A stable hash of daily run, channel, and recipient hash provides idempotency without storing the UID. Persistence failure, render/parity failure, missing directions, duplicate directions, or a failed chunk prevents the delivery from being marked complete.

Phase 11I-A keeps `EVIDENCE_FIRST_WXPUSHER_ENABLED=false`; no message is sent.
