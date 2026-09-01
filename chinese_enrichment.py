"""Post-membership factual Chinese enrichment with durable identity caching."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from time import perf_counter

from pydantic import BaseModel

import db
from ai_providers import AIProviderError, GeminiProvider

VERSION = "family-zh-v3"
MODEL = "gemini-3.5-flash-lite"
PROMPT = """Translate only the supplied factual product identities into concise natural Simplified Chinese. Return exactly one result per family_id. name_zh is a plain product name, preferably within 25 Chinese characters. description_zh is one concise factual sentence answering 'what is this?', preferably within 70 Chinese characters. Preserve brands and model names when present. Do not add opportunity judgments, recommendations, demand, profitability, suppliers, costs, differentiation, imagined audiences, advantages, or facts absent from the input."""
PROBE_PROMPT = """Translate this factual product identity into concise Simplified Chinese. Return a plain Chinese product name and one factual sentence answering what it is. Do not add recommendations, demand, profit, suppliers, or invented facts."""
PROHIBITED = (
    "巨大商机", "市场潜力", "值得销售", "建议进入", "高利润", "爆款", "盈利",
    "huge market", "profitable", "business opportunity", "recommend selling",
)

# Deliberately limited to common, unambiguous product phrases.  Replacements
# preserve every unmatched brand/model token verbatim.
PHRASE_TRANSLATIONS = (
    ("flying trap refills", "飞虫诱捕器替换芯"),
    ("metal platform bed frame", "金属平台床架"), ("solid-state battery", "固态电池"),
    ("desk fan", "桌面风扇"), ("portable", "便携"),
    ("full length mirror", "全身镜"), ("ac shade", "空调遮阳罩"),
    ("mole repellent", "驱鼹鼠器"), ("grow mushrooms", "蘑菇种植套件"),
    ("multitool", "多功能工具"), ("keyboard", "键盘"),
    ("pants", "裤子"), ("chair", "椅子"), ("dock", "扩展坞"),
    ("tents", "帐篷"),
    ("ring", "戒指"), ("case", "收纳盒"),
    ("cordless leaf blower", "无绳吹叶机"), ("insulated tumbler", "保温杯"),
    ("manual can opener", "手动开罐器"), ("expandable garden hose", "伸缩花园水管"),
    ("garden hose", "花园水管"), ("silicone food bag", "硅胶食品袋"),
    ("magnetic clips", "磁吸夹"), ("fridge magnets", "冰箱磁贴"),
    ("fruit fly trap", "果蝇诱捕器"), ("flying insect trap", "飞虫诱捕器"),
    ("insect trap refill", "昆虫诱捕器替换芯"), ("watering can", "浇水壶"),
    ("window clings", "窗贴"), ("window stickers", "窗户贴纸"),
    ("dragonfly clips", "蜻蜓装饰夹"), ("seed packets", "种子包"),
    ("running shoe", "跑鞋"), ("travel toothbrush", "旅行牙刷"),
    ("toothbrush", "牙刷"),
    ("electric toothbrush", "电动牙刷"), ("travel headphones", "旅行耳机"),
    ("split keyboard", "分体键盘"), ("mechanical keyboard", "机械键盘"),
    ("electric kettle", "电热水壶"), ("travel pillow", "旅行枕"),
    ("sleeping bag", "睡袋"), ("smart lamp", "智能灯"),
    ("smart battery hub", "智能电池中心"), ("battery banks", "充电宝"),
    ("batteries & chargers", "电池与充电器"), ("battery", "电池"),
    ("multi-tool ruler", "多功能尺"), ("multi-tool", "多功能工具"),
    ("pocket tool", "口袋工具"), ("ai pen", "AI 记录笔"),
    ("litter box", "猫砂盆"), ("ergonomic chair", "人体工学椅"),
    ("gaming chair", "游戏椅"), ("pocket camera", "口袋相机"),
    ("panoramic camera", "全景相机"), ("home camera", "家用摄像头"),
    ("convertible jacket", "可转换夹克"), ("garment steamer", "挂烫机"),
    ("overnight oats containers", "隔夜燕麦容器"), ("storage drawers", "储物抽屉"),
    ("rodent repellent", "驱鼠剂"), ("mouse rodent repellent", "驱鼠剂"),
    ("air freshener spray", "空气清新喷雾"), ("meat thermometer", "肉类温度计"),
    ("foil shaver", "往复式剃须刀"), ("coffee maker", "咖啡机"),
    ("phone case", "手机壳"), ("camera bag", "相机包"),
    ("companion bag", "随身包"), ("duffle", "旅行袋"),
    ("backpack", "背包"), ("tent", "帐篷"), ("cot", "行军床"),
    ("scissors", "剪刀"), ("wallet", "钱包"), ("watches", "腕表"),
    ("watch", "腕表"), ("pillow covers", "枕套"), ("pillow", "枕头"),
    ("serving tray", "餐盘"), ("folding fan", "折叠扇"),
    ("food printer", "食品打印机"), ("inkjet printer", "喷墨打印机"),
    ("3d printer", "3D 打印机"), ("mower", "割草机"),
    ("vr shoes", "VR 鞋"), ("cutting boards", "砧板"),
    ("lunchbox", "午餐盒"), ("cable", "线缆收纳器"),
    ("hydrration shirt", "补水运动衫"), ("hydration shirt", "补水运动衫"),
    ("keg", "啤酒桶系统"), ("spray", "喷雾器"),
)

SOFTWARE_SUFFIXES = (
    (r"\bapp\b", "应用"), (r"\bapplication\b", "应用"),
    (r"\btool\b", "工具"), (r"\bmanager\b", "管理工具"),
    (r"\btracker\b", "追踪工具"), (r"\beditor\b", "编辑器"),
    (r"\bgenerator\b", "生成工具"), (r"\bworkspace\b", "工作区"),
    (r"\bextension\b", "扩展"), (r"\bserver\b", "服务器"),
    (r"\bviewer\b", "查看器"), (r"\brecorder\b", "录制工具"),
    (r"\banalyzer\b", "分析工具"), (r"\bplatform\b", "平台"),
)


class TranslationItem(BaseModel):
    family_id: int
    name_zh: str
    description_zh: str


class TranslationBatch(BaseModel):
    items: list[TranslationItem]


class TranslationProbe(BaseModel):
    name_zh: str
    description_zh: str


@dataclass
class ProbeResult:
    success: bool
    latency: float
    model: str
    status: str
    error_type: str = ""
    message: str = ""
    result: TranslationProbe | None = None


def identity_fingerprint(item: dict) -> str:
    payload = "\n".join((
        str(item.get("canonical_name", "")).strip(),
        str(item.get("factual_description", "")).strip(),
        str(item.get("product_type", "")).strip(),
    ))
    return sha256(payload.encode("utf-8")).hexdigest()


def has_chinese(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value or ""))


def deterministic_name(item: dict) -> tuple[str, bool]:
    """Translate only high-confidence nouns while preserving brand/model text."""
    original = " ".join(str(item.get("canonical_name", "")).split())
    kind = str(item.get("product_type", "")).upper()
    design_specials = (
        ("Bandai Built a $22 Mecha Case", "Bandai 机甲名片盒"),
        ("ZWO Seestar S50 Pro", "ZWO Seestar S50 Pro 相机包"),
        ("Urwerk Built a Hand-Carved Pocket Watch", "Urwerk 手工雕刻怀表"),
        ("Bandai Just Made the Tamagotchi a Ring", "Bandai Tamagotchi 戒指"),
    )
    product_specials = (
        ("Pocket Hose Ballistic 100 FT", "Pocket Hose Ballistic 100 FT 伸缩花园水管"),
        ("DeliOne Duo Lock Pro", "DeliOne Duo Lock Pro 硅胶食品袋"),
        ("Avelo: Meet the world's smartest running shoe", "Avelo 跑鞋"),
    )
    for marker, value in product_specials:
        if marker.casefold() in original.casefold():
            return value, True
    if "Oral-B iO Series".casefold() in original.casefold() and "toothbrush" in original.casefold():
        return "Oral-B iO 系列牙刷", True
    if kind == "PRODUCT_DESIGN":
        for marker, value in design_specials:
            if marker.casefold() in original.casefold():
                return value, True
    # A source may have a coarse software label despite an explicit physical
    # noun in its title. Translation follows the factual noun without changing
    # the stored product type.
    if kind == "SOFTWARE_PRODUCT":
        for phrase, chinese in PHRASE_TRANSLATIONS:
            if phrase in {"toothbrush", "litter box", "keyboard", "meat thermometer", "food printer", "portable"}:
                match = re.search(rf"\b{re.escape(phrase)}\b", original, re.I)
                if match:
                    prefix = original[:match.start()].strip(" :-—")
                    brand = prefix.split(":")[-1].strip() if ":" in prefix else prefix.split()[0] if prefix else ""
                    return f"{brand} {chinese}".strip(), True
    if kind == "SOFTWARE_PRODUCT":
        base = re.split(r"\s+[—–-]\s+|:\s+", original, maxsplit=1)[0].strip()
        translated = base
        for pattern, chinese in SOFTWARE_SUFFIXES:
            if re.search(pattern, translated, re.I):
                translated = re.sub(pattern, chinese, translated, flags=re.I)
        if not has_chinese(translated):
            translated = f"{base} 软件"
        return translated, True

    def safe_prefix(prefix: str) -> str:
        cleaned = re.sub(r"[^\w+.-]+", " ", prefix, flags=re.UNICODE).strip()
        tokens = cleaned.split()
        if not tokens:
            return ""
        bad = {"does", "what", "why", "recommendation", "recommended", "recommend", "advice", "choosing", "new", "anyone", "looking", "from", "everybody"}
        if tokens[0].casefold() in bad:
            return ""
        if tokens[0].casefold() == "the":
            tokens = tokens[1:]
        if not tokens:
            return ""
        if tokens[0].casefold() == "portable":
            return "便携" + (" USB" if len(tokens) > 1 and tokens[1].upper() == "USB" else "")
        if tokens[:3] == ["5", "in", "1"]:
            return "5合1"
        if tokens[0].isdigit() and (len(tokens) == 1 or tokens[1].casefold() == "pack"):
            return ""
        first = tokens[0]
        output = [first]
        second_stop = {"ultra", "luxury", "real", "digital", "titanium", "the", "built", "mechanical"}
        if len(tokens) > 1 and tokens[1].casefold() not in second_stop and (
            any(char.isdigit() for char in tokens[1])
            or tokens[1].isupper()
            or (first.isupper() and tokens[1][0].isupper())
            or (first[0].isupper() and tokens[1][0].isupper() and tokens[1].casefold() not in {"ultra", "luxury", "real", "digital", "titanium"})
        ):
            output.append(tokens[1])
        model = next((token for token in reversed(tokens[2:]) if any(char.isdigit() for char in token)), "")
        if model and model not in output and len(model) <= 16:
            output.append(model)
        return " ".join(output)

    translated = original
    for phrase, chinese in PHRASE_TRANSLATIONS:
        pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.I)
        match = pattern.search(original)
        if match:
            prefix = safe_prefix(original[:match.start()])
            translated = f"{prefix} {chinese}".strip()
            break
    if kind == "PRODUCT_DESIGN" and not has_chinese(translated):
        translated = f"{original} 产品设计"
    translated = re.sub(r"\s+", " ", translated).strip(" -—|:")
    return translated, has_chinese(translated)


def deterministic_description(item: dict, name_zh: str) -> tuple[str, bool]:
    """Generate a conservative type statement without inferring capabilities."""
    if not has_chinese(name_zh):
        return str(item.get("factual_description", "")), False
    kind = str(item.get("product_type", "")).upper()
    physical_markers = ("牙刷", "猫砂盆", "键盘", "温度计", "打印机")
    if kind == "SOFTWARE_PRODUCT" and not any(marker in name_zh for marker in physical_markers):
        return f"一款名为{name_zh}的软件产品。", True
    if kind == "PRODUCT_DESIGN":
        return f"一项名为{name_zh}的产品设计。", True
    return f"该产品为{name_zh}。", True


def apply_deterministic_fallback(dataset: dict) -> dict:
    """Cache and apply safe deterministic language without changing membership."""
    stats = {"cache_hits": 0, "deterministic_names": 0, "deterministic_descriptions": 0, "english_only": 0}
    for item in dataset["items"]:
        fingerprint = identity_fingerprint(item)
        deterministic_version = VERSION + "-deterministic"
        cached = db.get_family_enrichment(item["family_id"], fingerprint, deterministic_version)
        if cached:
            name = cached["canonical_name_zh"]
            description = cached["factual_description_zh"]
            stats["cache_hits"] += 1
        else:
            name, name_ok = deterministic_name(item)
            description, description_ok = deterministic_description(item, name)
            if not (name_ok and description_ok):
                stats["english_only"] += 1
                continue
            if not db.save_family_enrichment(
                item["family_id"], fingerprint, item["canonical_name"], name, description,
                enrichment_version=deterministic_version,
            ):
                stats["english_only"] += 1
                continue
            stats["deterministic_names"] += 1
            stats["deterministic_descriptions"] += 1
        if db.update_daily_discovery_item_language(dataset["run_id"], item["family_id"], name, description):
            item["canonical_name_zh"] = name
            item["factual_description_zh"] = description
        else:
            stats["english_only"] += 1
    return stats


def validate_translation(value: TranslationItem, allowed_ids: set[int]) -> str | None:
    if value.family_id not in allowed_ids:
        return "UNKNOWN_FAMILY_ID"
    name = value.name_zh.strip()
    description = value.description_zh.strip()
    if not name or not description:
        return "EMPTY_CONTENT"
    if not has_chinese(name) or not has_chinese(description):
        return "ENGLISH_ECHO"
    combined = f"{name} {description}".casefold()
    if any(term.casefold() in combined for term in PROHIBITED):
        return "OPPORTUNITY_LANGUAGE"
    if len(name) > 50 or len(description) > 160:
        return "EXCESSIVE_LENGTH"
    return None


def safe_error(exc: Exception) -> dict:
    """Return useful non-secret SDK/HTTP diagnostics."""
    chain = []
    current: BaseException | None = exc
    while current and len(chain) < 4:
        chain.append({
            "type": type(current).__name__,
            "status": getattr(current, "status_code", None) or getattr(current, "code", None),
            "message": str(current)[:500],
        })
        current = current.__cause__ or current.__context__
    return {"chain": chain}


def connectivity_probe(provider: GeminiProvider) -> ProbeResult:
    started = perf_counter()
    try:
        raw = provider.analyze(
            {"english_name": "Manual Can Opener", "factual_description": "A handheld tool used to open metal cans."},
            PROBE_PROMPT, TranslationProbe, allow_retry=False,
        )
        parsed = TranslationProbe.model_validate_json(raw)
        if not (has_chinese(parsed.name_zh) and has_chinese(parsed.description_zh)):
            raise ValueError("Probe response did not contain Chinese")
        return ProbeResult(True, perf_counter() - started, provider.model_name, "SUCCESS", result=parsed)
    except Exception as exc:
        details = safe_error(exc)
        first = details["chain"][0]
        return ProbeResult(False, perf_counter() - started, provider.model_name, "FAILED", first["type"], json.dumps(details, ensure_ascii=False))


def select_representative(items: list[dict], limit: int = 20) -> list[dict]:
    """Deterministically spread the sample across source and evidence groups."""
    selected: list[dict] = []
    seen: set[int] = set()
    source_order = ("amazon", "kickstarter", "indiegogo", "product_hunt", "reddit_arctic_shift", "yanko_design", "hacker_news", "reddit_software")
    for evidence in ("STRONG", "MODERATE", "WEAK"):
        for source in source_order:
            match = next((item for item in items if item["family_id"] not in seen and item.get("evidence_strength") == evidence and source in item.get("source_platforms", [])), None)
            if match:
                selected.append(match); seen.add(match["family_id"])
                if len(selected) == limit:
                    return selected
    for item in items:
        if item["family_id"] not in seen:
            selected.append(item); seen.add(item["family_id"])
            if len(selected) == limit:
                break
    return selected


def apply_cached(dataset: dict) -> int:
    reused = 0
    for item in dataset["items"]:
        cached = db.get_family_enrichment(item["family_id"], identity_fingerprint(item), VERSION)
        if not cached:
            continue
        if db.update_daily_discovery_item_language(
            dataset["run_id"], item["family_id"], cached["canonical_name_zh"], cached["factual_description_zh"]
        ):
            item["canonical_name_zh"] = cached["canonical_name_zh"]
            item["factual_description_zh"] = cached["factual_description_zh"]
            reused += 1
    return reused


def enrich_items(provider: GeminiProvider, dataset: dict, items: list[dict], *, batch_size: int = 5) -> dict:
    stats = {"attempted": len(items), "succeeded": 0, "failed": 0, "requests": 0, "failures": []}
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        allowed = {item["family_id"]: item for item in batch}
        payload = {"items": [{
            "family_id": item["family_id"], "english_name": item["canonical_name"],
            "source_title": (item.get("source_records") or [{}])[0].get("source_title", ""),
            "factual_description": item.get("factual_description", "")[:350],
            "product_type": item.get("product_type", ""),
            "evidence": item.get("evidence_reasons", [])[:4],
        } for item in batch]}
        stats["requests"] += 1
        try:
            raw = provider.analyze(payload, PROMPT, TranslationBatch, allow_retry=False)
            response = TranslationBatch.model_validate_json(raw)
            returned: set[int] = set()
            for value in response.items:
                reason = validate_translation(value, set(allowed))
                if reason or value.family_id in returned:
                    stats["failures"].append({"family_id": value.family_id, "type": reason or "DUPLICATE_ID"})
                    continue
                item = allowed[value.family_id]
                name, description = value.name_zh.strip(), value.description_zh.strip()
                fingerprint = identity_fingerprint(item)
                saved = db.save_family_enrichment(
                    value.family_id, fingerprint, item["canonical_name"], name, description,
                    enrichment_version=VERSION,
                ) and db.update_daily_discovery_item_language(dataset["run_id"], value.family_id, name, description)
                if saved:
                    item["canonical_name_zh"] = name; item["factual_description_zh"] = description
                    returned.add(value.family_id); stats["succeeded"] += 1
            missing = set(allowed) - returned
            stats["failed"] += len(missing)
            stats["failures"].extend({"family_id": family_id, "type": "MISSING_OR_INVALID_RESULT"} for family_id in sorted(missing))
        except Exception as exc:
            stats["failed"] += len(batch)
            details = safe_error(exc)
            stats["failures"].extend({"family_id": item["family_id"], "type": type(exc).__name__, "details": details} for item in batch)
    return stats
