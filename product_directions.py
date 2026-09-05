"""Narrow, deterministic Product Direction aggregation for Daily Picks."""

from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import re

from user_voice import extract_user_voice, summarize_user_voice


DIRECTION_RULES = (
    (r"\bolight ostation 2\b", "smart-battery-management-hub", "Olight Ostation 2 Battery Hub", "智能电池管理与充电设备", "集中存放、检测并充电 AA/AAA 镍氢电池和兼容锂电池的电池管理设备。"),
    (r"\bweershun travel pillow\b", "chin-support-travel-pillow", "WEERSHUN Travel Pillow", "环绕下巴的记忆棉旅行颈枕", "通过环绕下巴的记忆棉结构为飞机、汽车和办公休息提供头颈支撑的旅行枕。"),
    (r"\bhoverair versa\b", "flying-pocket-camera", "HOVERAir VERSA", "可手持与自主飞行的口袋相机", "兼具手持拍摄和自主飞行模式的便携口袋相机，HOVERAir VERSA 保留为产品名。"),
    (r"\bnfc energy-harvesting pcb business card\b", "nfc-energy-harvesting-business-card", "NFC Energy-Harvesting Business Card", "NFC 能量采集电子名片", "利用 NFC 能量采集为板载微控制器供电的 PCB 电子名片。"),
    (r"\b5 in 1 convertible jacket\b", "convertible-jacket-backpack", "5-in-1 Convertible Jacket and Backpack", "五合一可转换夹克与背包", "可在夹克、背包、枕头或收纳形态之间转换的组合式随身产品。"),
    (r"\byeti rambler\b.*\bstraw mug\b", "insulated-straw-mug", "YETI Rambler Straw Mug", "带吸管的保温随行杯", "带吸管杯盖的保温随行杯，YETI Rambler 保留为代表产品名。"),
    (r"\bmet through sally\b", "interest-based-social-app", "Met Through Sally Social App", "兴趣匹配的线下社交应用", "根据共同兴趣帮助城市用户在线下认识他人的会员制社交应用。"),
    (r"\bstep stool\b.*\bentryway\b", "entryway-step-stool", "Entryway Step Stool", "适合玄关摆放的踏脚凳", "兼顾登高使用与玄关环境摆放的踏脚凳产品方向。"),
    (r"\banker mindbase\b", "camera-local-ai-storage-hub", "Anker MindBase Camera Hub", "摄像头 AI 本地存储中枢", "为兼容摄像头提供本地存储与 AI 处理能力的设备中枢，Anker MindBase 保留为产品名。"),
    (r"\bqwen\b|slotstream", "local-llm-low-memory", "Low-memory Mac Local LLM Tool", "低内存 Mac 本地大模型运行工具", "帮助内存受限的 Mac 在本地运行大语言模型的软件工具，具体兼容性以公开项目资料为准。"),
    (r"\bweedout\b", "youtube-ai-video-filter", "Weedout Browser Extension", "过滤 YouTube AI 生成视频的浏览器扩展", "Weedout 是用于识别或过滤 YouTube AI 生成视频的浏览器扩展；Weedout 保留为产品名。"),
    (r"\bowntime\b", "flexible-time-planner", "OwnTime Planning App", "灵活时间块与生活角色规划应用", "OwnTime 是用灵活时间块和生活角色组织日程的规划应用；OwnTime 保留为产品名。"),
    (r"\bwaltz\b", "room-scan-interior-design", "Waltz Interior Design App", "手机扫描房间的 AI 室内设计工具", "Waltz 是通过手机扫描房间并辅助室内设计的软件工具；Waltz 保留为产品名。"),
    (r"\bgpd win max 3\b", "oled-handheld-gaming-pc", "GPD WIN Max 3", "可更换电池的 OLED 掌上游戏电脑", "GPD WIN Max 3 是采用 OLED 屏幕和可更换电池设计的掌上游戏电脑。"),
    (r"\be[- ]?ink bike computer\b", "open-source-eink-bike-computer", "Open-source E-Ink Bike Computer", "开源电子墨水自行车码表", "使用电子墨水屏显示骑行信息的开源自行车码表。"),
    (r"\binsulated tumbler\b|\btumbler\b", "insulated-tumbler", "Insulated Tumbler", "保温杯", "双层保温的随身饮水容器，公开产品主要展示容量、杯盖、防漏和便携形态。"),
    (r"\bphone case\b|\botterbox\b.*\bcase\b", "phone-case", "Phone Case", "手机壳", "安装在手机外部的保护壳，公开资料涉及防摔、耐用性、结构磨损和保修体验。"),
    (r"\boutdoor rocking chair\b|\bpolywood\b.*\brock", "outdoor-rocking-chair", "Outdoor Rocking Chair", "户外摇椅", "适合门廊或庭院使用的摇椅，公开资料涉及户外耐候材料、结构耐久性和售后更换经历。"),
    (r"\bmattress\b|\bwinkbed luxury firm\b", "mattress", "Mattress", "床垫", "用于睡眠支撑的床垫，公开资料涉及软硬度、长期下陷、内部结构和保修处理。"),
    (r"\btent cot\b|\bcamping tent cot\b", "camping-tent-cot", "Camping Tent Cot", "帐篷行军床", "将离地行军床与单人遮蔽结构结合的露营装备，与普通地面帐篷保持独立方向。"),
    (r"\b(?:camping )?tent\b|\bwawona 6\b", "camping-tent", "Camping Tent", "露营帐篷", "用于户外露营的可搭建遮蔽结构，公开资料涉及空间、支杆、抗风和耐用性。"),
    (r"\bsleeping bag\b", "sleeping-bag", "Sleeping Bag", "睡袋", "用于露营和旅行睡眠保温的便携寝具，产品差异主要来自温标、填充材料、重量和收纳体积。"),
    (r"\bergonomic chair\b|\bdynamic ergonomic chair\b", "ergonomic-chair", "Ergonomic Chair", "人体工学椅", "为坐姿提供可调支撑的座椅，公开资料涉及靠背、坐姿调节、倾仰和支撑结构。"),
    (r"\b(?:portable )?(?:battery bank|power bank)\b", "portable-battery-bank", "Portable Battery Bank", "便携充电宝", "用于随身储存并输出电能的便携电源，公开资料涉及容量、接口、充电方式和体积。"),
    (r"\bmanual can opener\b", "manual-can-opener", "Manual Can Opener", "手动开罐器", "通过手动机械结构切开罐盖的厨房工具，主要结构包括握柄、切轮和传动部件。"),
    (r"\bwatering can\b", "watering-can", "Watering Can", "浇水壶", "用于给植物定向浇水的手持容器，产品形态围绕容量、壶嘴、防滴漏和握持设计。"),
    (r"\bflying insect trap\b|\bfruit fly trap\b", "flying-insect-trap", "Flying Insect Trap", "飞虫诱捕器", "用于室内捕捉果蝇、蚊虫等小型飞虫的装置，公开资料涉及诱捕光源、耗材和无电击式结构。"),
    (r"\bgarden hose\b|\bwater hose\b", "garden-hose", "Garden Hose", "花园水管", "用于庭院供水和浇灌的柔性水管，公开资料涉及长度、重量、抗打结和耐候性。"),
    (r"\bovernight oats containers?\b", "overnight-oats-container", "Overnight Oats Container", "隔夜燕麦容器", "用于分装、冷藏和携带隔夜燕麦的食品容器，常见结构包括密封盖和独立配件。"),
    (r"\bmeat thermometer\b", "meat-thermometer", "Meat Thermometer", "肉类温度计", "用于测量烹饪食材内部温度的手持工具，公开资料涉及探针、读数速度和显示方式。"),
    (r"\bfirecrawl\b", "ai-web-data-extraction", "AI Web Data Extraction Tool", "AI 网页数据提取工具", "面向开发者和 AI 应用的网页数据提取工具，可把公开网页内容转换为 Markdown 或结构化数据，供程序检索和处理。"),
    (r"\bmechanical keyboard\b|\bflow 2.*keyboard\b", "mechanical-keyboard", "Mechanical Keyboard", "机械键盘", "使用独立机械轴体输入的键盘，公开资料涉及布局、连接方式、结构手感和可定制性。"),
    (r"\bmulti-tool\b|\bmultitool\b", "multi-tool", "Multi-Tool", "多功能工具", "将多种日常工具组合进一个便携结构的随身工具，公开资料涉及材料、功能数量和折叠方式。"),
)


SINGLETON_DESCRIPTIONS = (
    (r"\bolight ostation 2\b", "Olight Ostation 2 是一款智能电池管理设备，可集中存放和充电 AA/AAA 镍氢电池及 Olight 1.5V 锂电池，并提供电池健康检测、无极性放置和快速充电功能。"),
    (r"\bweershun travel pillow\b", "WEERSHUN 旅行枕是一款用于飞机、办公室和汽车场景的记忆棉颈枕，通过环绕下巴的结构为头颈提供支撑。"),
    (r"\bhoverair versa\b", "HOVERAir VERSA 是一款可手持也可自主飞行的口袋相机，配有三轴云台、多种自动飞行模式，并以便携拍摄为主要使用场景。"),
    (r"\bmet through sally\b", "Met Through Sally 是一款会员制社交应用，面向希望根据共同兴趣在线下认识他人的城市用户，而不是依赖连续滑动匹配。"),
    (r"\bcognitive card games\b|\bx-squared\b", "X-Squared 是一套数学卡牌及配套数字应用，通过卡牌游戏和解题活动练习数学思维。"),
    (r"\bstaats\b", "Staats 是一款面向开发者的网站监测工具，让编程助手能够读取并回答网站运行情况。"),
    (r"\bbusiness cards were forgettable\b|\bmecha case\b", "Bandai 机甲名片盒是一款以机甲造型呈现的实体名片收纳盒，用于携带名片并在交换名片时展示机械结构外观。"),
    (r"\bzwo seestar s50 pro\b", "ZWO Seestar S50 Pro 是一套便携式智能天文摄影设备，把望远镜、相机与自动跟踪功能整合在可携带的机身中。"),
    (r"\bglisio\b", "Glisio 是一款 Mac 屏幕录制与截图编辑工具，支持自动缩放、音频录制，并在本地导出 MP4 文件。"),
    (r"\bscreenpipe\b", "screenpipe 是一款在本地记录电脑操作的工具，可将屏幕与工作过程数据提供给 AI 助手使用。"),
)


def _direction_rule(item: dict) -> tuple[str, str, str, str] | None:
    text = " ".join((str(item.get("canonical_name") or ""), str(item.get("factual_description") or ""))).casefold()
    for pattern, key, name_en, name_zh, description_zh in DIRECTION_RULES:
        if re.search(pattern, text, re.I):
            return key, name_en, name_zh, description_zh
    return None


def _useful_description(item: dict) -> str:
    chinese = str(item.get("factual_description_zh") or "").strip()
    if chinese and not re.match(r"^该产品为|^一款名为|^一项名为", chinese):
        return chinese
    identity = " ".join((str(item.get("canonical_name") or ""), str(item.get("factual_description") or "")))
    for pattern, description in SINGLETON_DESCRIPTIONS:
        if re.search(pattern, identity, re.I):
            return description
    factual = " ".join(str(item.get("factual_description") or "").split())[:180]
    kind = str(item.get("product_type") or "").upper()
    prefix = "公开资料描述的软件功能包括：" if kind == "SOFTWARE_PRODUCT" else "公开资料描述的功能和形态包括："
    return f"{prefix}{factual}" if factual else "当前仅有具体产品身份和来源记录，详细功能仍需查看原始来源。"


def _evidence_for_record(record: dict, family: dict) -> dict:
    source = str(record.get("source_platform") or "")
    raw = record.get("raw_data") if isinstance(record.get("raw_data"), dict) else {}
    facts = []
    if source == "amazon":
        if raw.get("rating") is not None: facts.append(f"{raw['rating']}★")
        if raw.get("review_count") is not None: facts.append(f"{raw['review_count']} reviews")
        if raw.get("rank") is not None: facts.append(f"rank {raw['rank']}")
        if raw.get("price"): facts.append(str(raw["price"]))
    elif source in {"kickstarter", "indiegogo"}:
        backers = raw.get("backers_count", raw.get("backer_count", raw.get("backers")))
        funded = raw.get("percent_funded", raw.get("funding_percentage"))
        if backers is not None: facts.append(f"{backers} backers")
        if funded is not None: facts.append(f"{funded:g}% funded" if isinstance(funded, (int, float)) else f"{funded}% funded")
    elif "reddit" in source:
        if raw.get("score") is not None: facts.append(f"score {raw['score']}")
        if raw.get("num_comments") is not None: facts.append(f"{raw['num_comments']} comments")
        if raw.get("subreddit"): facts.append(f"r/{raw['subreddit']}")
    elif source == "hacker_news":
        if raw.get("points") is not None: facts.append(f"{raw['points']} points")
        if raw.get("comment_count") is not None: facts.append(f"{raw['comment_count']} comments")
    elif source == "product_hunt":
        facts.append("Product Hunt product listing")
        if raw.get("tagline"): facts.append(str(raw["tagline"])[:100])
    elif source == "yanko_design":
        facts.append("Yanko Design editorial discovery")
        if raw.get("published_at"): facts.append(str(raw["published_at"]))
    else:
        facts.append("Public source record")
    return {
        "source": source, "family_id": int(family["family_id"]),
        "product_name": family.get("canonical_name"),
        "source_title": record.get("source_title"), "facts": facts,
        "url": str(record.get("url") or ""), "link_available": bool(record.get("url")),
    }


def build_product_directions(items: list[dict]) -> list[dict]:
    """Aggregate families into narrow directions while preserving every member."""
    groups: dict[str, list[dict]] = defaultdict(list)
    definitions: dict[str, tuple[str, str, str]] = {}
    for item in items:
        rule = _direction_rule(item)
        if rule:
            key, name_en, name_zh, description_zh = rule
            definitions[key] = (name_en, name_zh, description_zh)
        else:
            key = f"family:{int(item['family_id'])}"
            definitions[key] = (
                str(item.get("canonical_name") or "Unresolved product"),
                str(item.get("canonical_name_zh") or item.get("canonical_name") or "未解析产品"),
                _useful_description(item),
            )
        groups[key].append(item)

    output = []
    for key, members in groups.items():
        name_en, name_zh, description_zh = definitions[key]
        representative = sorted(members, key=lambda item: (int(item.get("display_order", 10**9)), int(item["family_id"])))[0]
        evidence = [_evidence_for_record(record, member) for member in members for record in member.get("source_records", [])]
        voice = []
        for member in members:
            voice.extend(extract_user_voice(member))
        # Summarizer provides exact-text/source dedupe.
        summary = summarize_user_voice(voice)
        unique_voice = []
        seen_voice = set()
        for value in voice:
            marker = (value.get("original_text"), value.get("source_url"))
            if marker not in seen_voice:
                seen_voice.add(marker); unique_voice.append(value)
        strength_order = {"STRONG": 0, "MODERATE": 1, "WEAK": 2}
        evidence_strength = min(
            (str(item.get("evidence_strength") or "WEAK").upper() for item in members),
            key=lambda value: strength_order.get(value, 3),
        )
        known_rule = not key.startswith("family:")
        output.append({
            **representative,
            "direction_id": "direction:" + sha256(key.encode("utf-8")).hexdigest()[:16],
            "direction_key": key, "name_en": name_en, "name_zh": name_zh,
            "description_en": str(representative.get("factual_description") or ""),
            "description_zh": description_zh,
            "canonical_name": name_en, "canonical_name_zh": name_zh,
            "member_family_ids": [int(item["family_id"]) for item in members],
            "member_product_identities": [str(item.get("canonical_name") or "") for item in members],
            "representative_products": [str(item.get("canonical_name") or "") for item in members],
            "source_platforms": sorted({source for item in members for source in item.get("source_platforms", [])}),
            "source_records": [record for item in members for record in item.get("source_records", [])],
            "evidence_strength": evidence_strength,
            "evidence_reasons": list(dict.fromkeys(reason for item in members for reason in item.get("evidence_reasons", []))),
            "source_evidence": evidence, "user_voice": unique_voice,
            "user_voice_summary": summary,
            "aggregation_method": "narrow_product_noun_rule" if len(members) > 1 else "singleton",
            "aggregation_reason": f"Members share the specific {name_en} product direction." if len(members) > 1 else "No safely comparable family was found; retained as a singleton direction.",
            "aggregation_confidence": "HIGH" if len(members) > 1 else "MEDIUM",
            "identity_valid": True if known_rule else bool(representative.get("identity_valid", True)),
            "identity_confidence": "HIGH" if known_rule else representative.get("identity_confidence", "MEDIUM"),
        })
    return output
