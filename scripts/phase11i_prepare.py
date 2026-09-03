"""Prepare Phase 11I previews and exercise additive persistence locally only."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def approved_payload() -> dict:
    from daily_direction_report import prepare_daily_payload
    folder = ROOT / ".phase11h-preview"
    picks = json.loads((folder / "selected_daily_picks.json").read_text(encoding="utf-8"))
    voice = json.loads((folder / "final_user_voice_render.json").read_text(encoding="utf-8"))
    by_direction = {value["direction_id"]: value["items"] for value in voice}
    for item in picks["items"]:
        item["user_voice"] = by_direction.get(item["direction_id"], [])
    picks.setdefault("run_id", "picks:" + str(picks["daily_discovery_run_id"]))
    return prepare_daily_payload(picks)


def persistence_validation(payload: dict) -> dict:
    import db
    from database_backend import DatabaseSettings
    original_path, original_settings = db.DB_PATH, db.DATABASE_SETTINGS
    with tempfile.TemporaryDirectory(prefix="phase11i-", ignore_cleanup_errors=True) as folder:
        path = Path(folder) / "validation.db"
        db.DB_PATH = path
        db.DATABASE_SETTINGS = DatabaseSettings("sqlite", "", path)
        try:
            assert db.init_db()
            discovery_run = str(payload["daily_discovery_run_id"])
            pipeline_run = "phase11i-validation"
            with db._connect() as connection:
                now = "2026-09-02T00:00:00+00:00"
                connection.execute("INSERT INTO pipeline_runs(run_id,started_at,status,error,stats_json) VALUES (?,?,?,'','{}')", (pipeline_run, now, "SUCCESS"))
                connection.execute("INSERT INTO daily_discovery_runs(run_id,pipeline_run_id,discovery_date,generated_at,status,item_count,metadata_json) VALUES (?,?,?,?,?,?,?)", (discovery_run,pipeline_run,"2026-09-02",now,"COMPLETED",payload["item_count"],"{}"))
                family_ids = sorted({int(fid) for item in payload["items"] for fid in item.get("member_family_ids", [item["family_id"]])})
                for fid in family_ids:
                    connection.execute("""INSERT INTO product_families(id,family_key,canonical_name,canonical_name_zh,primary_category,product_type,first_seen_at,last_seen_at,status,grouping_version,created_at,updated_at) VALUES (?,?,?,?,?,'PHYSICAL_PRODUCT',?,?,'ACTIVE','test',?,?)""", (fid,f"family-{fid}",f"Family {fid}",None,"",now,now,now,now))
            run_id = db.persist_daily_picks_snapshot(discovery_run, payload["items"], payload.get("requested_count",20))
            reloaded = db.get_persisted_daily_picks(run_id=run_id)
            before = json.loads(json.dumps(reloaded["items"], ensure_ascii=False, sort_keys=True, default=str))
            with db._connect() as connection:
                connection.execute("UPDATE product_directions SET name_en='SIMULATED CHANGE'")
            after = db.get_persisted_daily_picks(run_id=run_id)["items"]
            counts = {}
            with db._connect() as connection:
                for table in ("product_directions","product_direction_members","daily_picks_runs","daily_picks_items"):
                    counts[table] = connection.execute(f"SELECT COUNT(*) count FROM {table}").fetchone()["count"]
            return {"daily_run_can_be_saved":bool(run_id),"daily_run_can_be_reloaded":bool(reloaded),
                "reloaded_order_identical":[x["direction_id"] for x in before]==[x["direction_id"] for x in after],
                "reloaded_directions_identical":before==after,"representative_members_identical":all(a.get("representative_products")==b.get("representative_products") for a,b in zip(before,after)),
                "evidence_identical":all(a.get("source_evidence")==b.get("source_evidence") for a,b in zip(before,after)),
                "user_voice_identical":all(a.get("user_voice")==b.get("user_voice") for a,b in zip(before,after)),
                "historical_snapshot_survives_underlying_change":before==after,"counts":counts,
                "production_writes":0,"overall":bool(run_id and reloaded and before==after),
                "_reloaded_payload":reloaded}
        finally:
            db.DB_PATH, db.DATABASE_SETTINGS = original_path, original_settings


def generate(output: Path) -> dict:
    from daily_direction_report import render_web_today, render_wxpusher_messages, validate_web_wxpusher_parity
    payload = approved_payload(); output.mkdir(parents=True, exist_ok=True)
    persistence = persistence_validation(payload)
    render_payload = persistence.pop("_reloaded_payload")
    web = render_web_today(render_payload); messages = render_wxpusher_messages(render_payload)
    parity = validate_web_wxpusher_parity(render_payload, messages)
    (output/"web_today_preview.html").write_text(web,encoding="utf-8")
    (output/"wxpusher_full_preview.html").write_text("<meta charset='utf-8'>"+"<hr>".join(x["content"] for x in messages),encoding="utf-8")
    (output/"wxpusher_messages.json").write_text(json.dumps(messages,ensure_ascii=False,indent=2),encoding="utf-8")
    (output/"web_wxpusher_parity.json").write_text(json.dumps(parity,ensure_ascii=False,indent=2),encoding="utf-8")
    (output/"daily_persistence_validation.json").write_text(json.dumps(persistence,ensure_ascii=False,indent=2),encoding="utf-8")
    return {"directions":payload["item_count"],"messages":len(messages),"parity":parity["overall"],"persistence":persistence["overall"]}


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--dry-run",action="store_true"); parser.add_argument("--output",type=Path,default=ROOT/".phase11i-preview")
    args=parser.parse_args(); result=generate(args.output)
    print(json.dumps({"mode":"dry-run" if args.dry_run else "local-preview","production_writes":0,**result}))
    return 0 if result["parity"] and result["persistence"] else 1

if __name__=="__main__": raise SystemExit(main())
