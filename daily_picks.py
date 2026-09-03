"""Deterministic, diverse Daily Picks derived from Daily Discovery."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import math
import re

import db
from evidence_foundation import normalize_reddit_title, reddit_identity_chinese
from product_directions import build_product_directions
from user_voice import (
    extract_user_voice, faithful_chinese_translation, normalize_user_voice_items,
    select_feedback_excerpt, summarize_user_voice,
)


SOURCE_CAPS = {
    "amazon": 4, "kickstarter": 4, "indiegogo": 3,
    "reddit": 3, "reddit_arctic_shift": 3, "reddit_software": 4,
    "product_hunt": 4, "hacker_news": 4, "yanko_design": 2,
}
EVIDENCE_RANK = {"STRONG": 0, "MODERATE": 1, "WEAK": 2}
NON_PRODUCT_PICK_PATTERNS = (
    r"\bshort film\b", r"\bfeature film\b", r"\bmovie\b", r"\bfilm festival\b",
    r"\balbum\b", r"\bdonation\b", r"\btrip report\b", r"\bitinerary\b",
    r"\bbag dump\b", r"\bpacking list\b",
)
PRODUCT_OBJECT_HINTS = (
    "bag", "backpack", "jacket", "camera", "chair", "keyboard", "tool", "blade",
    "tumbler", "bottle", "clip", "magnet", "watering can", "lamp", "holder",
    "case", "pillow", "wallet", "organizer", "shoe", "device", "battery",
)
SOFTWARE_OBJECT_HINTS = ("software", "app", "platform", "dashboard", "browser", "extension", "api", "tool")
SOFTWARE_SPECIFIC_HINTS = SOFTWARE_OBJECT_HINTS + (
    "agent", "model", "editor", "recorder", "workspace", "developer", "automation",
)
SOURCE_LABELS = {
    "amazon": "Amazon", "kickstarter": "Kickstarter", "indiegogo": "Indiegogo",
    "reddit": "Reddit", "reddit_arctic_shift": "Reddit", "reddit_software": "Software Reddit",
    "product_hunt": "Product Hunt", "hacker_news": "Hacker News",
    "yanko_design": "Yanko Design",
}
BASKET_ORDER = (
    "市场已验证", "其他产品发现", "用户需求与问题", "软件 / 数字产品", "设计与探索",
)
BASKET_TARGETS = {
    "市场已验证": 5, "其他产品发现": 4, "用户需求与问题": 4,
    "软件 / 数字产品": 4, "设计与探索": 3,
}


def primary_source(item: dict) -> str:
    sources = list(item.get("source_platforms") or [])
    return str(sources[0] if sources else "other").casefold()


def source_display_label(source: str) -> str:
    """Return a stable user-facing label without changing canonical IDs."""
    return SOURCE_LABELS.get(str(source).casefold(), str(source))


def available_source_options(items: list[dict]) -> list[tuple[str, str]]:
    """Return represented canonical IDs and labels only."""
    sources = sorted({str(source) for item in items for source in item.get("source_platforms", [])})
    return [(source, source_display_label(source)) for source in sources]


def prepare_discovery_item(item: dict) -> dict:
    """Correct Reddit display identity in-memory while preserving source titles."""
    value = dict(item)
    records = [dict(record) for record in item.get("source_records", [])]
    value["source_records"] = records
    reddit_records = [record for record in records if "reddit" in str(record.get("source_platform", "")).casefold()]
    if not reddit_records:
        value.setdefault("identity_confidence", "MEDIUM")
        value.setdefault("identity_valid", bool(value.get("canonical_name")))
        return value
    identities = []
    for record in reddit_records:
        normalized = normalize_reddit_title(
            str(record.get("source_title") or ""), str(record.get("description") or ""),
        )
        if normalized:
            identities.append(normalized)
    if identities and len(set(identities)) == 1:
        normalized = identities[0]
        value["canonical_name"] = normalized
        value["canonical_name_zh"] = reddit_identity_chinese(normalized) or value.get("canonical_name_zh")
        value["identity_confidence"] = "HIGH"
        value["identity_valid"] = True
        value["identity_method"] = "reddit_product_noun"
    else:
        value["identity_confidence"] = "LOW"
        value["identity_valid"] = False
        value["identity_method"] = "reddit_unresolved"
        # Do not translate or overwrite the original discussion sentence.
        value["canonical_name_zh"] = None
    return value


def _numeric_signals(item: dict) -> dict[str, float]:
    values: dict[str, float] = {}
    for record in item.get("source_records", []):
        raw = record.get("raw_data") if isinstance(record.get("raw_data"), dict) else {}
        for key in ("review_count", "rating", "rank", "rank_change", "backers", "backers_count", "backer_count", "funding_percentage", "percent_funded", "score", "num_comments", "points", "comment_count"):
            value = raw.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values[key] = max(values.get(key, float("-inf")), float(value))
    return values


def _engagement(item: dict) -> float:
    values = _numeric_signals(item)
    source = primary_source(item)
    if source == "amazon":
        return math.log1p(max(0, values.get("review_count", 0))) + values.get("rating", 0)
    if source in {"kickstarter", "indiegogo"}:
        return math.log1p(max(0, values.get("backers", values.get("backers_count", values.get("backer_count", 0))))) + math.log1p(max(0, values.get("funding_percentage", values.get("percent_funded", 0))))
    if "reddit" in source:
        return math.log1p(max(0, values.get("score", 0))) + math.log1p(max(0, values.get("num_comments", 0)))
    if source == "hacker_news":
        return math.log1p(max(0, values.get("points", 0))) + math.log1p(max(0, values.get("comment_count", 0)))
    return 0.0


def _software_specificity(item: dict) -> int:
    if str(item.get("product_type") or "").upper() != "SOFTWARE_PRODUCT":
        return 0
    text = " ".join((str(item.get("canonical_name") or ""), str(item.get("factual_description") or ""))).casefold()
    return sum(bool(re.search(rf"\b{re.escape(hint)}s?\b", text)) for hint in SOFTWARE_SPECIFIC_HINTS)


def _is_product_pick(item: dict) -> bool:
    if not item.get("identity_valid", True):
        return False
    text = " ".join((str(item.get("canonical_name") or ""), str(item.get("factual_description") or ""))).casefold()
    if any(re.search(pattern, text) for pattern in NON_PRODUCT_PICK_PATTERNS):
        return False
    if primary_source(item) in {"kickstarter", "indiegogo"}:
        hints = SOFTWARE_OBJECT_HINTS if item.get("product_type") == "SOFTWARE_PRODUCT" else PRODUCT_OBJECT_HINTS
        return any(re.search(rf"\b{re.escape(hint)}s?\b", text) for hint in hints)
    return True


def _basket(item: dict) -> str:
    source = primary_source(item)
    kind = str(item.get("product_type") or "").upper()
    strength = str(item.get("evidence_strength") or "WEAK").upper()
    if kind == "SOFTWARE_PRODUCT":
        return "软件 / 数字产品"
    if kind == "PRODUCT_DESIGN" or source == "yanko_design":
        return "设计与探索"
    if "reddit" in source:
        return "用户需求与问题"
    if strength == "STRONG" and source in {"amazon", "kickstarter", "indiegogo"}:
        return "市场已验证"
    return "其他产品发现"


def _near_duplicate_key(item: dict) -> str | None:
    """Conservative Picks-only key for obvious interchangeable product nouns."""
    text = str(item.get("canonical_name") or "").casefold()
    rules = (
        (r"\binsulated tumbler\b|\btumbler\b", "insulated-tumbler"),
        (r"\bmanual can opener\b", "manual-can-opener"),
        (r"\bwatering can\b", "watering-can"),
    )
    return next((key for pattern, key in rules if re.search(pattern, text)), None)


def selection_reasons(item: dict, *, exploration: bool = False) -> list[str]:
    reasons: list[str] = []
    strength = str(item.get("evidence_strength") or "WEAK").upper()
    if strength == "STRONG":
        reasons.append("市场信号较强")
    values = _numeric_signals(item)
    source = primary_source(item)
    comments = values.get("num_comments", values.get("comment_count", 0))
    backers = values.get("backers", values.get("backers_count", values.get("backer_count", 0)))
    if ("reddit" in source or source == "hacker_news") and comments >= 5:
        reasons.append("用户讨论较多")
    if source in {"kickstarter", "indiegogo"} and backers >= 50:
        reasons.append("众筹支持较多")
    if exploration:
        reasons.append("探索发现")
    if not reasons:
        reasons.append("近期发现")
    return reasons


def select_daily_picks(dataset: dict, *, target: int = 20, exploration_slots: int = 2) -> list[dict]:
    """Select balanced factual products without AI or platform quotas."""
    prepared = [prepare_discovery_item(item) for item in dataset.get("items", [])]
    directions = build_product_directions(prepared)
    candidates = sorted((item for item in directions if _is_product_pick(item)), key=lambda item: (
        EVIDENCE_RANK.get(str(item.get("evidence_strength", "WEAK")).upper(), 3),
        -_engagement(item), -_software_specificity(item),
        int(item.get("display_order", 10**9)), int(item.get("family_id", 0)),
    ))
    selected: list[dict] = []
    counts: dict[str, int] = {}
    used: set[int] = set()
    duplicate_keys: set[str] = set()

    def add(item: dict) -> bool:
        family_id = int(item["family_id"]); source = primary_source(item)
        duplicate_key = _near_duplicate_key(item)
        if family_id in used or counts.get(source, 0) >= SOURCE_CAPS.get(source, 2):
            return False
        if duplicate_key and duplicate_key in duplicate_keys:
            return False
        selected.append(dict(item)); used.add(family_id); counts[source] = counts.get(source, 0) + 1
        if duplicate_key:
            duplicate_keys.add(duplicate_key)
        return True

    for basket in BASKET_ORDER:
        pool = [item for item in candidates if _basket(item) == basket]
        for item in pool:
            strength = str(item.get("evidence_strength") or "WEAK").upper()
            # Concrete software may enter with factual weak discovery evidence;
            # weak evidence is never relabeled as market validation.
            if strength == "WEAK" and basket not in {"软件 / 数字产品", "设计与探索"}:
                continue
            add(item)
            if sum(_basket(value) == basket for value in selected) >= BASKET_TARGETS[basket]:
                break
    # Quality-preserving fill to the target. Weak entries remain confined to
    # software/design baskets and obvious duplicates stay in Full Discovery.
    for item in candidates:
        if len(selected) >= target:
            break
        basket = _basket(item)
        if str(item.get("evidence_strength") or "WEAK").upper() == "WEAK" and basket not in {"软件 / 数字产品", "设计与探索"}:
            continue
        add(item)
    for order, item in enumerate(selected, 1):
        item["pick_order"] = order
        item["primary_source"] = primary_source(item)
        item["basket"] = _basket(item)
        item["selection_reasons"] = selection_reasons(item, exploration=item["basket"] == "设计与探索")
        item["user_voice"] = list(item.get("user_voice") or [])
        item["user_voice_summary"] = summarize_user_voice(item["user_voice"])
    return selected


def build_daily_picks(dataset: dict, *, persist: bool = True, target: int = 20) -> dict:
    items = select_daily_picks(dataset, target=target)
    voice_by_family = {}
    for item in dataset.get("items", []):
        family_id = int(item["family_id"])
        stored = db.get_user_voice_items(family_id) if persist else []
        voice_by_family[family_id] = normalize_user_voice_items(stored) if stored else extract_user_voice(item)
    for item in items:
        item["user_voice"] = [
            voice for family_id in item.get("member_family_ids", [item["family_id"]])
            for voice in voice_by_family.get(int(family_id), [])
        ]
        display_types = {"AUTHOR_EXPERIENCE":"原帖使用体验", "USER_NEED":"用户需求",
            "PRODUCT_DISCUSSION":"产品讨论", "DISCUSSION_TEXT":"产品讨论",
            "COMMENTER_FEEDBACK":"评论区反馈", "PRODUCT_REVIEW":"产品评价"}
        prepared_voice = []
        for voice in item["user_voice"]:
            value = dict(voice)
            value["original_text"] = select_feedback_excerpt(str(value.get("original_text") or ""))
            value["translated_text_zh"] = value.get("translated_text_zh") or faithful_chinese_translation(value["original_text"])
            value["product_direction_id"] = item["direction_id"]
            value["display_type_zh"] = display_types.get(str(value.get("voice_type") or ""), "真实反馈")
            if value.get("original_text") and value.get("source_url"):
                prepared_voice.append(value)
        item["user_voice"] = prepared_voice[:5]
        item["user_voice_summary"] = summarize_user_voice(item["user_voice"])
    result = {
        "daily_discovery_run_id": dataset["run_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "full_discovery_count": len(dataset.get("items", [])),
        "item_count": len(items), "items": items,
        "requested_count": target,
        "shortage_reason": "" if len(items) >= target else (
            f"Only {len(items)} qualified distinct product directions remained after identity, evidence, source-cap, and narrow-aggregation checks."
        ),
    }
    if persist:
        from daily_direction_report import prepare_daily_payload
        result = prepare_daily_payload(result)
        result["run_id"] = db.persist_daily_picks_snapshot(dataset["run_id"], result["items"], target)
        db.save_user_voice_items([voice for item in result["items"] for voice in item.get("user_voice", [])])
    return result


def load_daily_picks(**identity: str) -> dict | None:
    return db.get_persisted_daily_picks(**identity)


def today_pick_items(dataset: dict) -> list[dict]:
    return list(dataset.get("items", []))


def render_wxpusher_pick_chunks(dataset: dict, *, items_per_chunk: int = 10) -> list[dict]:
    items = list(dataset.get("items", [])); chunks = []
    total = math.ceil(len(items) / items_per_chunk) if items else 0
    for index in range(total):
        subset = items[index * items_per_chunk:(index + 1) * items_per_chunk]
        blocks = []
        for item in subset:
            reasons = "；".join(item.get("selection_reasons", []))
            blocks.append(f"<p><b>{item['pick_order']}. {escape(str(item.get('canonical_name_zh') or item['canonical_name']))}</b><br><small>{escape(str(item['canonical_name']))}</small><br>为什么今天展示：{escape(reasons)}<br>Evidence: {escape(str(item.get('evidence_strength')))}</p>")
        chunks.append({"title": f"今日值得看 {index + 1}/{total}", "content": "\n".join(blocks), "family_ids": [int(item["family_id"]) for item in subset], "items": subset})
    return chunks
