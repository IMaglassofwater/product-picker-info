"""Generate local-only Phase 11H Product Direction previews and audits."""
from __future__ import annotations

from collections import Counter
from html import escape
import json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

VOICE_LABELS = {"AUTHOR_EXPERIENCE":"原帖使用体验", "USER_NEED":"用户需求",
    "PRODUCT_DISCUSSION":"产品讨论", "DISCUSSION_TEXT":"产品讨论",
    "COMMENTER_FEEDBACK":"评论区反馈", "PRODUCT_REVIEW":"产品评价"}
NECESSARY_TERMS = re.compile(r"\b(?:Olight|AA|AAA|Ni-MH|Li-ion|WEERSHUN|HOVERAir|Met Through Sally|X-Squared|Staats|Bandai|ZWO|Seestar|Firecrawl|Markdown|Glisio|Mac|MP4|screenpipe|AI)\b", re.I)
ENGLISH_PROBLEM = re.compile(r"\b(?:provides?|compatible|battery|health|check|storage|charging|camera|flight|members?|social|developer|tool|website|business|card|recorder|editor|audio|local|artifacts?)\b", re.I)


def _ph_samples(folder: Path) -> list[dict]:
    path = folder / "producthunt_feedback_samples.json"
    return list(json.loads(path.read_text(encoding="utf-8")).get("samples") or []) if path.exists() else []


def _visible_voice(item: dict, ph_samples: list[dict]) -> list[dict]:
    from user_voice import faithful_chinese_translation, select_feedback_excerpt
    values = [dict(v) for v in item.get("user_voice", [])]
    if item.get("direction_key") == "ai-web-data-extraction":
        values += [{"source":"product_hunt", "voice_type":"PRODUCT_REVIEW",
            "original_text":v.get("original_text"), "translated_text_zh":v.get("translated_text_zh"),
            "author":v.get("author"), "published_at":v.get("timestamp"), "source_url":v.get("source_url"),
            "source_item_id":v.get("source_id"), "identity_key":v.get("source_id") or "ph-review-text"} for v in ph_samples]
    selected, seen, per_source = [], set(), Counter()
    for value in values:
        original = select_feedback_excerpt(str(value.get("original_text") or ""))
        translated = str(value.get("translated_text_zh") or "").strip() or faithful_chinese_translation(original)
        source, url = str(value.get("source") or ""), str(value.get("source_url") or "")
        trace = str(value.get("source_item_id") or value.get("identity_key") or "")
        marker = (original, url)
        if not all((original, translated, url, trace)) or marker in seen or per_source[source] >= 3: continue
        seen.add(marker); per_source[source] += 1
        selected.append({**value, "original_text":original, "translated_text_zh":translated, "trace_id":trace})
        if len(selected) == 5: break
    return selected


def _render_voice(item: dict, ph_samples: list[dict], label) -> tuple[str, list[dict]]:
    values = _visible_voice(item, ph_samples)
    if not values:
        url = next((e.get("url") for e in item.get("source_evidence", []) if e.get("source") in {"kickstarter","indiegogo"} and e.get("url")), None)
        suffix = f' · <a href="{escape(str(url), quote=True)}">查看平台项目</a>' if url else ""
        return f'<p class="empty-feedback">暂无可用的真实文字反馈{suffix}</p>', []
    html = []
    for v in values:
        meta = f'{escape(str(v.get("author") or "公开用户"))} · {escape(str(v.get("published_at") or "时间未公开"))}'
        html.append(f'<section class="voice"><small>{escape(label(str(v.get("source") or "")))} · {escape(VOICE_LABELS.get(str(v.get("voice_type") or ""), "真实反馈"))}</small>'
            f'<p class="voice-zh">{escape(str(v["translated_text_zh"]))}</p>'
            f'<p class="voice-en" lang="en">{escape(str(v["original_text"]))}</p>'
            f'<div class="voice-meta">{meta} · <a href="{escape(str(v["source_url"]), quote=True)}">查看原文</a></div></section>')
    return "".join(html), values


def _evidence(item: dict, label) -> str:
    grouped = {}
    for e in item.get("source_evidence", []): grouped.setdefault(str(e["source"]), []).append(e)
    sections = []
    for source, values in grouped.items():
        rows = []
        for e in values:
            facts = " · ".join(map(str, e.get("facts", []))) or "公开来源记录"
            link = f' · <a href="{escape(str(e["url"]), quote=True)}">查看来源</a>' if e.get("link_available") else ""
            rows.append(f'<li>{escape(str(e.get("product_name") or ""))} — {escape(facts)}{link}</li>')
        sections.append(f'<h4>{escape(label(source))}</h4><ul>{"".join(rows)}</ul>')
    return "".join(sections)


def write_previews(output_dir: Path, discovery: dict, picks: dict) -> dict:
    from daily_picks import source_display_label
    from user_voice import extract_user_voice
    output_dir.mkdir(parents=True, exist_ok=True)
    items, samples = picks["items"], _ph_samples(output_dir)
    all_voice = {int(i["family_id"]):extract_user_voice(i) for i in discovery["items"]}
    rendered, cards = {}, []
    for item in items:
        feedback, voices = _render_voice(item, samples, source_display_label); rendered[item["direction_id"]] = voices
        products = "".join(f'<li>{escape(str(x))}</li>' for x in item.get("representative_products", []))
        cards.append(f'<article data-direction-id="{escape(str(item["direction_id"]))}"><h2>{item["pick_order"]}. {escape(str(item["name_zh"]))}</h2>'
            f'<p class="direction-en">{escape(str(item["name_en"]))}</p><h3>这是什么</h3><p>{escape(str(item["description_zh"]))}</p>'
            f'<h3>代表产品</h3><ul>{products}</ul><h3>市场佐证</h3>{_evidence(item, source_display_label)}'
            f'<h3>用户反馈 / 评论区反馈</h3>{feedback}</article>')
    css = "<meta charset='utf-8'><style>body{font-family:system-ui;max-width:1000px;margin:auto;color:#222}article{border:1px solid #ddd;border-radius:12px;padding:18px;margin:14px}.direction-en,.voice-en,.voice-meta,small{color:#6b7280}.voice{border-left:3px solid #ddd;padding:8px 14px;margin:14px 0}.voice-zh{font-size:1.04rem;line-height:1.75}.voice-en{line-height:1.55}.empty-feedback{color:#777}</style>"
    today = css + f'<h1>今日值得看 · {len(items)} 个产品方向</h1><p>今日完整发现包含 {discovery["item_count"]} 个产品家族</p>' + "".join(cards)
    (output_dir/"today_picks_preview.html").write_text(today, encoding="utf-8")
    full_cards=[]
    for item in discovery["items"]:
        feedback,_ = _render_voice({**item,"user_voice":all_voice[int(item["family_id"])]}, samples, source_display_label)
        full_cards.append(f'<article><h2>{escape(str(item.get("canonical_name_zh") or item["canonical_name"]))}</h2><p class="direction-en">{escape(str(item["canonical_name"]))}</p><p>{escape(str(item.get("factual_description_zh") or item.get("factual_description") or "暂无事实描述"))}</p><h3>用户反馈 / 评论区反馈</h3>{feedback}</article>')
    full = css + f'<h1>完整发现（{discovery["item_count"]}）</h1>' + "".join(full_cards)
    (output_dir/"full_discovery_preview.html").write_text(full, encoding="utf-8")

    aggregation=[{"direction":i["name_en"],"direction_zh":i["name_zh"],"matched_platforms":i.get("source_platforms",[]),
        "matched_products_families":[{"family_id":fid,"product":p} for fid,p in zip(i.get("member_family_ids",[]),i.get("member_product_identities",[]))],
        "match_reason":i.get("aggregation_reason"),"confidence":i.get("aggregation_confidence")} for i in items]
    voice=[{"direction_id":i["direction_id"],"direction":i["name_en"],"items":rendered.get(i["direction_id"],[])} for i in items]
    desc=[]
    for i in items:
        value=str(i.get("description_zh") or ""); problem=bool(ENGLISH_PROBLEM.search(NECESSARY_TERMS.sub("",value)))
        desc.append({"direction":i["name_en"],"description_zh":value,"natural_chinese":not problem,"necessary_mixed_terms":NECESSARY_TERMS.findall(value),"unnecessary_english":problem})
    desc_audit={"audited":len(items),"natural_chinese":sum(x["natural_chinese"] for x in desc),"necessary_mixed_terms":sum(bool(x["necessary_mixed_terms"]) for x in desc),"unnecessary_english_remaining":sum(x["unnecessary_english"] for x in desc),"problematic_directions":[x["direction"] for x in desc if x["unnecessary_english"]],"items":desc}
    all_visible = [voice_item for values in rendered.values() for voice_item in values]
    tumbler = next((i for i in items if i.get("direction_key") == "insulated-tumbler"), {})
    thermometer = next((i for i in items if i.get("direction_key") == "meat-thermometer"), {})
    tent = next((i for i in items if i.get("direction_key") == "camping-tent"), {})
    validation={"direction_count":today.count('data-direction-id='),"required_sections":all(x in today for x in ("这是什么","代表产品","市场佐证","用户反馈 / 评论区反馈")),"why_selected_absent":"为什么今天展示" not in today,"internal_type_absent":"PHYSICAL_PRODUCT" not in today,"representative_products":today.count("<h3>代表产品</h3>")==len(items),"platform_grouped_evidence":today.count("<h3>市场佐证</h3>")==len(items),"real_user_voice_items":today.count('class="voice"'),"average_visible_chinese_length":round(sum(len(str(x.get("translated_text_zh") or "")) for x in all_visible)/len(all_visible),1) if all_visible else 0,"feedback_with_english_original":sum(bool(x.get("original_text")) for x in all_visible),"feedback_with_traceable_source":sum(bool(x.get("source_url") and x.get("trace_id")) for x in all_visible),"chinese_primary":'class="voice-zh"' in today,"english_secondary":'class="voice-en"' in today,"traceable_sources":today.count("查看原文")==today.count('class="voice"'),"redundant_labels":{x:today.count(x) for x in ("中文翻译：","English Original：","作者：")},"polywood_actual_text":"Friends, I totally have to gush" in today,"otterbox_actual_text":"old OtterBox Defender Series" in today,"winkbed_actual_text":"WinkBed Luxury Firm" in full and "我使用的 WinkBed" in full,"kelty_actual_text":"I used to recommend Kelty" in today,"camping_tent_types":sorted({x.get("voice_type") for x in rendered.get(tent.get("direction_id"),[])}),"product_hunt_real_reviews":"Pranav Pai Vernekar" in today and "Summarized with AI" not in today,"medium_length_feedback":any(len(str(x.get("translated_text_zh") or ""))>=60 for x in all_visible),"single_empty_state":"暂无可用的真实文字反馈" in today,"insulated_tumbler_aggregation":set(tumbler.get("representative_products",[]))=={"Frost Insulated Tumbler","Simple Insulated Tumbler","STANLEY Insulated Tumbler"},"meat_thermometer_cross_platform":set(thermometer.get("source_platforms",[]))=={"amazon","kickstarter"},"unnecessary_english_remaining":desc_audit["unnecessary_english_remaining"]}
    diversity={"selected":len(items),"sources":Counter(i["primary_source"] for i in items),"types":Counter(i["product_type"] for i in items),"multi_member_directions":sum(len(i.get("member_family_ids",[]))>1 for i in items),"singleton_directions":sum(len(i.get("member_family_ids",[]))==1 for i in items)}
    for name,value in {"selected_daily_picks.json":picks,"daily_picks_diversity.json":diversity,"final_direction_platform_aggregation.json":aggregation,"final_user_voice_render.json":voice,"final_description_chinese_audit.json":desc_audit,"final_preview_validation.json":validation}.items():
        (output_dir/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=lambda x:dict(x)),encoding="utf-8")
    return {"diversity":diversity,"description_audit":desc_audit,"validation":validation,"platform_aggregation":aggregation}


def main() -> int:
    if not os.getenv("DATABASE_URL"): raise SystemExit("DATABASE_URL is required")
    import db
    from daily_picks import build_daily_picks, prepare_discovery_item
    discovery=db.get_persisted_daily_discovery()
    if not discovery: raise SystemExit("Persisted Daily Discovery is missing")
    discovery={**discovery,"items":[prepare_discovery_item(i) for i in discovery["items"]]}
    report=write_previews(ROOT/".phase11h-preview",discovery,build_daily_picks(discovery,persist=False))
    print(json.dumps({"full":discovery["item_count"],**report},ensure_ascii=False,default=lambda x:dict(x)))
    return 0

if __name__ == "__main__": raise SystemExit(main())
