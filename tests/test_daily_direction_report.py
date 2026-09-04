"""Phase 11I persisted direction and full-fidelity renderer tests."""
from copy import deepcopy
import json

import pytest

from daily_direction_report import (
    prepare_daily_payload, render_web_today, render_wxpusher_messages,
    validate_notification_snapshot, validate_web_wxpusher_parity,
)
from wxpusher_notifier import WxPusherNotifier, notification_delivery_key, send_full_fidelity_daily
from database_backend import DatabaseSettings


def direction(index=1, *, members=None, sources=None, voice=None):
    members = members or ["Frost Insulated Tumbler", "Simple Insulated Tumbler", "STANLEY Insulated Tumbler"]
    sources = sources or ["amazon"]
    return {"family_id":index,"direction_id":f"direction:stable-{index}","direction_key":f"direction-{index}",
        "pick_order":index,"name_en":"Insulated Tumbler","name_zh":"保温杯","description_zh":"双层保温的随身饮水容器。",
        "product_type":"PHYSICAL_PRODUCT","representative_products":members,"member_family_ids":list(range(index,index+len(members))),
        "source_platforms":sources,"source_evidence":[{"source":source,"family_id":index,"product_name":members[0],"facts":["4.7★"],"url":f"https://example.test/{source}"} for source in sources],
        "user_voice":voice or []}


def payload(items=None):
    values=items or [direction()]
    return {"run_id":"picks:daily:test","daily_discovery_run_id":"daily:test","item_count":len(values),"items":values}


def review():
    return {"identity_key":"review:1","source":"product_hunt","voice_type":"PRODUCT_REVIEW","display_type_zh":"产品评价",
        "translated_text_zh":"这款工具能可靠提取网页数据。","original_text":"This tool reliably extracts web data.","author":"Public Reviewer",
        "published_at":"2026-09-02","source_url":"https://example.test/review/1"}


def test_notification_snapshot_integrity_gate_accepts_complete_payload():
    messages, parity = validate_notification_snapshot(payload([direction(voice=[review()])]))
    assert len(messages) == 1
    assert parity["overall"] is True


def test_notification_snapshot_integrity_gate_rejects_missing_translation_and_duplicates():
    missing = payload([direction(voice=[review()])])
    missing["items"][0]["user_voice"][0]["translated_text_zh"] = ""
    with pytest.raises(ValueError, match="Chinese User Voice"):
        validate_notification_snapshot(missing)

    duplicate = payload([direction(1), direction(1)])
    with pytest.raises(ValueError, match="duplicate Direction"):
        validate_notification_snapshot(duplicate)


def test_stable_ids_members_singletons_and_cross_platform_evidence():
    first=prepare_daily_payload(payload([direction(sources=["amazon","kickstarter"])]))
    second=prepare_daily_payload(payload([direction(sources=["amazon","kickstarter"])]))
    assert first["items"][0]["direction_id"]==second["items"][0]["direction_id"]
    assert len(first["items"][0]["representative_products"])==3
    assert {x["source"] for x in first["items"][0]["source_evidence"]}=={"amazon","kickstarter"}
    assert len(prepare_daily_payload(payload([direction(members=["Singleton"])]))["items"][0]["representative_products"])==1


def test_meat_thermometer_and_tumbler_regressions_are_representable():
    meat=direction(10,members=["Amazon Meat Thermometer","Kickstarter Meat Thermometer"],sources=["amazon","kickstarter"])
    meat.update(direction_key="meat-thermometer",name_en="Meat Thermometer",name_zh="肉类温度计")
    values=prepare_daily_payload(payload([direction(),meat]))["items"]
    assert values[0]["representative_products"]==["Frost Insulated Tumbler","Simple Insulated Tumbler","STANLEY Insulated Tumbler"]
    assert set(values[1]["source_platforms"])=={"amazon","kickstarter"}


def test_real_review_and_reddit_original_translation_are_preserved_and_deduplicable():
    item=direction(voice=[review()]); data=prepare_daily_payload(payload([item]))
    stored=data["items"][0]["user_voice"][0]
    assert stored["translated_text_zh"] and stored["original_text"].startswith("This tool")
    assert stored["user_voice_id"]==prepare_daily_payload(payload([item]))["items"][0]["user_voice"][0]["user_voice_id"]


def test_web_renderer_preserves_structure_links_and_escapes_html():
    item=direction(voice=[{**review(),"original_text":"Useful <script>alert(1)</script>"}])
    html=render_web_today(payload([item]))
    assert all(value in html for value in ("这是什么","代表产品","市场佐证","用户反馈 / 评论区反馈"))
    assert "https://example.test/review/1" in html and "<script>" not in html and "&lt;script&gt;" in html


def test_wxpusher_is_full_fidelity_and_splits_without_loss_or_duplicates():
    items=[{**direction(i,members=[f"Product {i}"]),"pick_order":i} for i in range(1,7)]
    data=payload(items); messages=render_wxpusher_messages(data,max_chars=1000)
    ids=[value for message in messages for value in message["direction_ids"]]
    assert len(messages)>1 and ids==[item["direction_id"] for item in items] and len(ids)==len(set(ids))
    assert validate_web_wxpusher_parity(data,messages)["overall"]


def test_historical_payload_is_a_deep_snapshot():
    source=payload(); frozen=prepare_daily_payload(source); source["items"][0]["name_zh"]="已变化"
    assert frozen["items"][0]["name_zh"]=="保温杯"


def test_notification_identity_never_contains_raw_recipient():
    key,recipient_hash=notification_delivery_key("daily:test","UID-sensitive")
    assert "UID-sensitive" not in key and "UID-sensitive" not in recipient_hash and key==notification_delivery_key("daily:test","UID-sensitive")[0]


def test_full_send_is_idempotent_and_records_all_chunks():
    sent=[]; records=[]
    notifier=WxPusherNotifier("token","uid",post=lambda *a,**k:None)
    notifier.send=lambda title,content,**kwargs: sent.append((title,content)) or True
    data=payload([direction(1,members=["One"]),direction(2,members=["Two"])])
    assert send_full_fidelity_daily(data,notifier=notifier,record_delivery=lambda *x:records.append(x),max_chars=700)
    key,_=notification_delivery_key("picks:daily:test","uid")
    before=len(sent)
    assert send_full_fidelity_daily(data,notifier=notifier,is_delivered=lambda value:value==key)
    assert len(sent)==before and records[-1][-1]==records[-1][-2]


def test_parity_failure_prevents_send(monkeypatch):
    sent=[]; notifier=WxPusherNotifier("token","uid"); notifier.send=lambda *a,**k:sent.append(1) or True
    monkeypatch.setattr("daily_direction_report.validate_web_wxpusher_parity",lambda *a,**k:{"overall":False})
    assert not send_full_fidelity_daily(payload(),notifier=notifier) and sent==[]


def test_full_discovery_and_favorite_data_are_not_mutated_by_rendering():
    data=payload(); data["favorite_family_ids"]=[1]; before=json.dumps(data,sort_keys=True)
    render_web_today(data); render_wxpusher_messages(data)
    assert json.dumps(data,sort_keys=True)==before and data["favorite_family_ids"]==[1]


def test_additive_migration_is_idempotent_dry_and_preserves_product_and_favorite(tmp_path, monkeypatch):
    import db
    path=tmp_path/"migration.db"
    monkeypatch.setattr(db,"DB_PATH",path); monkeypatch.setattr(db,"DATABASE_SETTINGS",DatabaseSettings("sqlite","",path))
    assert db.init_db()
    with db._connect() as connection:
        connection.execute("INSERT INTO products(project_id,source_platform,url,title,description,category,image_url,raw_data) VALUES ('p','amazon','https://example.test/p','P','D','C','','{}')")
        connection.execute("INSERT INTO user_product_feedback(entity_type,entity_id,feedback_type,note,created_at,updated_at) VALUES ('product','1','FAVORITE','',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
    assert db.init_db()
    with db._connect() as connection:
        assert connection.execute("SELECT COUNT(*) count FROM products").fetchone()["count"]==1
        assert connection.execute("SELECT COUNT(*) count FROM user_product_feedback WHERE feedback_type='FAVORITE'").fetchone()["count"]==1
        tables={x["name"] for x in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"product_directions","product_direction_members","notification_deliveries"}<=tables


def test_postgres_migration_contains_additive_direction_schema():
    from postgres_backend import POSTGRES_SCHEMA, evidence_schema_statements
    sql="\n".join(evidence_schema_statements())
    assert all(name in POSTGRES_SCHEMA for name in ("product_directions","product_direction_members","notification_deliveries"))
    assert "DROP TABLE" not in sql.upper()


def test_report_under_default_character_limit_is_one_full_fidelity_message():
    data=payload([{**direction(i,members=[f"Product {i}"],voice=[review()]),"pick_order":i} for i in range(1,21)])
    messages=render_wxpusher_messages(data)
    assert len(messages)==1 and messages[0]["direction_count"]==20
    assert messages[0]["character_count"]==len(messages[0]["content"])<=39000
    assert "This tool reliably extracts web data." in messages[0]["content"]
    assert "https://example.test/review/1" in messages[0]["content"]
    assert validate_web_wxpusher_parity(data,messages)["overall"]


def test_character_limit_does_not_penalize_multibyte_chinese_content():
    item=direction(); item["description_zh"]="中"*400
    messages=render_wxpusher_messages(payload([item]),max_chars=1000)
    assert len(messages)==1 and len(messages[0]["content"])<1000
    assert len(messages[0]["content"].encode("utf-8"))>1000


def test_oversized_report_splits_only_between_complete_directions():
    items=[]
    for index in range(1,5):
        item=direction(index,members=[f"Product {index}"],voice=[review()])
        item["description_zh"]="说明"*180
        items.append(item)
    data=payload(items); messages=render_wxpusher_messages(data,max_chars=1500)
    ids=[value for message in messages for value in message["direction_ids"]]
    assert len(messages)>1 and ids==[item["direction_id"] for item in items]
    assert len(ids)==len(set(ids)) and all(len(message["content"])<=1500 for message in messages)
    assert all(message["content"].count("<article data-direction-id=")==message["direction_count"] for message in messages)
    assert validate_web_wxpusher_parity(data,messages)["overall"]


def test_single_oversized_direction_fails_explicitly_without_sending():
    item=direction(); item["description_zh"]="超长"*1000
    data=payload([item])
    try:
        render_wxpusher_messages(data,max_chars=500)
    except ValueError as exc:
        assert item["direction_id"] in str(exc)
    else:
        raise AssertionError("oversized direction must fail explicitly")
    sent=[]; warnings=[]
    notifier=WxPusherNotifier("token","uid",warning=warnings.append)
    notifier.send=lambda *args,**kwargs: sent.append(args) or True
    assert not send_full_fidelity_daily(data,notifier=notifier,max_chars=500)
    assert not sent and "exceeds WxPusher safe character limit" in warnings[0]
