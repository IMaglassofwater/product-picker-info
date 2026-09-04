"""Full-fidelity renderers over one persisted Daily Product Direction snapshot."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from html import escape
import json
from typing import Iterable

REPORT_VERSION = "daily-direction-report-v1"
DEFAULT_WXPUSHER_MAX_CHARS = 39000


def _stable_id(prefix: str, value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}:{sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def prepare_daily_payload(dataset: dict) -> dict:
    """Freeze render identities inside a self-contained historical snapshot."""
    output = deepcopy(dataset)
    output["render_version"] = REPORT_VERSION
    for order, item in enumerate(output.get("items", []), 1):
        item["pick_order"] = int(item.get("pick_order") or order)
        item["direction_id"] = str(item["direction_id"])
        for evidence in item.get("source_evidence", []):
            evidence.setdefault("evidence_id", _stable_id("evidence", {
                "direction": item["direction_id"], "source": evidence.get("source"),
                "family_id": evidence.get("family_id"), "url": evidence.get("url"),
                "facts": evidence.get("facts", []),
            }))
        for voice in item.get("user_voice", []):
            voice.setdefault("user_voice_id", str(voice.get("identity_key") or voice.get("trace_id") or
                                                   _stable_id("voice", {"url": voice.get("source_url"), "text": voice.get("original_text")})))
    return output


def _market_evidence(item: dict) -> str:
    grouped: dict[str, list[dict]] = {}
    for value in item.get("source_evidence", []):
        grouped.setdefault(str(value.get("source") or "Other"), []).append(value)
    sections = []
    for platform, values in grouped.items():
        rows = []
        for value in values:
            facts = " · ".join(map(str, value.get("facts", []))) or "公开来源记录"
            link = f' · <a href="{escape(str(value["url"]), quote=True)}">查看来源</a>' if value.get("url") else ""
            rows.append(f'<li data-evidence-id="{escape(str(value["evidence_id"]), quote=True)}">{escape(str(value.get("product_name") or ""))} — {escape(facts)}{link}</li>')
        sections.append(f'<h4>{escape(platform)}</h4><ul>{"".join(rows)}</ul>')
    return "".join(sections)


def _voice(item: dict) -> str:
    values = item.get("user_voice", [])
    if not values:
        return '<p class="empty-feedback">暂无可用的真实文字反馈</p>'
    output = []
    for value in values:
        source = escape(str(value.get("source") or "公开来源"))
        kind = escape(str(value.get("display_type_zh") or value.get("voice_type") or "真实反馈"))
        author = escape(str(value.get("author") or "公开用户"))
        when = escape(str(value.get("published_at") or "时间未公开"))
        url = escape(str(value.get("source_url") or ""), quote=True)
        output.append(f'<section class="voice" data-voice-id="{escape(str(value["user_voice_id"]), quote=True)}"><small>{source} · {kind}</small>'
            f'<p class="voice-zh">{escape(str(value.get("translated_text_zh") or ""))}</p>'
            f'<p class="voice-en" lang="en">{escape(str(value.get("original_text") or ""))}</p>'
            f'<div class="voice-meta">{author} · {when}' + (f' · <a href="{url}">查看原文</a>' if url else "") + '</div></section>')
    return "".join(output)


def render_direction(item: dict) -> str:
    products = "".join(f"<li>{escape(str(value))}</li>" for value in item.get("representative_products", []))
    return (f'<article data-direction-id="{escape(str(item["direction_id"]), quote=True)}">'
        f'<h2>{item["pick_order"]}. {escape(str(item.get("name_zh") or item.get("canonical_name_zh") or ""))}</h2>'
        f'<p class="direction-en">{escape(str(item.get("name_en") or item.get("canonical_name") or ""))}</p>'
        f'<h3>这是什么</h3><p>{escape(str(item.get("description_zh") or "暂无事实描述"))}</p>'
        f'<h3>代表产品</h3><ul>{products}</ul><h3>市场佐证</h3>{_market_evidence(item)}'
        f'<h3>用户反馈 / 评论区反馈</h3>{_voice(item)}</article>')


def render_web_today(dataset: dict) -> str:
    data = prepare_daily_payload(dataset)
    css = "<meta charset='utf-8'><style>body{font-family:system-ui;max-width:1000px;margin:auto;color:#222}article{border:1px solid #ddd;border-radius:12px;padding:18px;margin:14px}.direction-en,.voice-en,.voice-meta,small{color:#6b7280}.voice{border-left:3px solid #ddd;padding:8px 14px;margin:14px 0}.voice-zh{font-size:1.04rem;line-height:1.75}.voice-en{line-height:1.55}.empty-feedback{color:#777}</style>"
    return css + f'<main data-daily-run-id="{escape(str(data.get("run_id") or data.get("daily_discovery_run_id") or ""), quote=True)}"><h1>今日值得看 · {len(data.get("items", []))} 个产品方向</h1>' + "".join(render_direction(item) for item in data.get("items", [])) + "</main>"


def render_wxpusher_messages(dataset: dict, *, max_chars: int = DEFAULT_WXPUSHER_MAX_CHARS) -> list[dict]:
    """Render full fidelity, splitting between directions only when required."""
    data = prepare_daily_payload(dataset)
    cards = [(item["direction_id"], render_direction(item)) for item in data.get("items", [])]
    if not cards:
        return []

    complete_content = "<h1>今日产品发现 1/1</h1>" + "".join(card for _, card in cards)
    if len(complete_content) <= max_chars:
        return [{"message_index": 1, "total_messages": 1,
            "direction_ids": [value[0] for value in cards], "direction_count": len(cards),
            "content": complete_content, "character_count": len(complete_content),
            "utf8_bytes": len(complete_content.encode("utf-8"))}]

    # Reserve a worst-case chunk heading while grouping. The final content is
    # checked again below, so the configured limit always applies to the exact
    # string sent to WxPusher rather than to an estimate or encoded byte size.
    heading_reserve = len(f"<h1>今日产品发现 {len(cards)}/{len(cards)}</h1>")
    groups: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    size = heading_reserve
    for pair in cards:
        card_size = len(pair[1])
        if heading_reserve + card_size > max_chars:
            raise ValueError(f"Product Direction exceeds WxPusher safe character limit: {pair[0]}")
        if current and size + card_size > max_chars:
            groups.append(current); current = []; size = heading_reserve
        current.append(pair); size += card_size
    if current: groups.append(current)
    total = len(groups)
    messages = []
    for index, group in enumerate(groups, 1):
        content = f"<h1>今日产品发现 {index}/{total}</h1>" + "".join(value[1] for value in group)
        if len(content) > max_chars:
            raise ValueError(f"WxPusher message exceeds safe character limit: chunk {index}")
        messages.append({"message_index": index, "total_messages": total,
            "direction_ids": [value[0] for value in group], "direction_count": len(group),
            "content": content, "character_count": len(content),
            "utf8_bytes": len(content.encode("utf-8"))})
    return messages


def _projection(dataset: dict) -> dict:
    data = prepare_daily_payload(dataset)
    return {"run_id": data.get("run_id") or data.get("daily_discovery_run_id"),
        "directions": [{"id": item["direction_id"], "products": list(item.get("representative_products", [])),
            "evidence": [(e["evidence_id"], e.get("url")) for e in item.get("source_evidence", [])],
            "voice": [(v["user_voice_id"], v.get("translated_text_zh"), v.get("original_text"), v.get("source_url")) for v in item.get("user_voice", [])]}
            for item in data.get("items", [])]}


def validate_web_wxpusher_parity(dataset: dict, messages: Iterable[dict]) -> dict:
    expected = _projection(dataset); ids = [value["id"] for value in expected["directions"]]
    message_ids = [direction_id for message in messages for direction_id in message["direction_ids"]]
    combined = "".join(message["content"] for message in messages)
    checks = {
        "same_daily_run": bool(expected["run_id"]), "same_direction_ids": ids == message_ids,
        "same_direction_order": ids == message_ids, "same_direction_count": len(ids) == len(message_ids),
        "same_representative_products": all(escape(str(p)) in combined for d in expected["directions"] for p in d["products"]),
        "same_evidence_ids": all(eid in combined for d in expected["directions"] for eid, _ in d["evidence"]),
        "same_evidence_count": combined.count("data-evidence-id=") == sum(len(d["evidence"]) for d in expected["directions"]),
        "same_user_voice_ids": all(vid in combined for d in expected["directions"] for vid, *_ in d["voice"]),
        "same_user_voice_count": combined.count("data-voice-id=") == sum(len(d["voice"]) for d in expected["directions"]),
        "same_user_voice_chinese_text": all(escape(str(zh)) in combined for d in expected["directions"] for _, zh, _, _ in d["voice"]),
        "same_user_voice_english_original": all(escape(str(en)) in combined for d in expected["directions"] for _, _, en, _ in d["voice"]),
        "same_source_urls": all(not url or escape(str(url), quote=True) in combined for d in expected["directions"] for _, url in d["evidence"]) and all(not url or escape(str(url), quote=True) in combined for d in expected["directions"] for *_, url in d["voice"]),
        "no_direction_missing_from_wxpusher": set(ids) == set(message_ids),
        "no_direction_duplicated_in_wxpusher": len(message_ids) == len(set(message_ids)),
    }
    return {**checks, "overall": all(checks.values()), "direction_count": len(ids),
            "directions_missing": sorted(set(ids)-set(message_ids)),
            "directions_duplicated": sorted({value for value in message_ids if message_ids.count(value)>1})}


def validate_notification_snapshot(
    dataset: dict, *, max_chars: int = DEFAULT_WXPUSHER_MAX_CHARS,
    require_single_message: bool = False,
) -> tuple[list[dict], dict]:
    """Fail closed unless a persisted Daily snapshot is complete and render-safe."""
    data = prepare_daily_payload(dataset)
    items = list(data.get("items") or [])
    if not data.get("run_id") or not items:
        raise ValueError("persisted Daily snapshot is missing or empty")

    direction_ids = [str(item.get("direction_id") or "") for item in items]
    if any(not value for value in direction_ids) or len(direction_ids) != len(set(direction_ids)):
        raise ValueError("Daily snapshot contains missing or duplicate Direction IDs")

    voice_ids: list[str] = []
    for item in items:
        if not (item.get("name_zh") or item.get("canonical_name_zh")):
            raise ValueError(f"missing Chinese name for Direction {item['direction_id']}")
        if not item.get("description_zh"):
            raise ValueError(f"missing Chinese description for Direction {item['direction_id']}")
        for voice in item.get("user_voice") or []:
            voice_id = str(voice.get("user_voice_id") or "")
            if not voice_id or voice_id in voice_ids:
                raise ValueError("Daily snapshot contains missing or duplicate User Voice IDs")
            voice_ids.append(voice_id)
            if not voice.get("translated_text_zh"):
                raise ValueError(f"missing Chinese User Voice translation: {voice_id}")
            if not voice.get("original_text"):
                raise ValueError(f"missing English User Voice original: {voice_id}")
            if not voice.get("source_url"):
                raise ValueError(f"missing User Voice source URL: {voice_id}")

    messages = render_wxpusher_messages(data, max_chars=max_chars)
    if require_single_message and len(messages) != 1:
        raise ValueError(
            f"acceptance report requires {len(messages)} messages; expected exactly one"
        )
    parity = validate_web_wxpusher_parity(data, messages)
    if not parity.get("overall"):
        raise ValueError("Web and WxPusher report parity validation failed")
    return messages, parity
