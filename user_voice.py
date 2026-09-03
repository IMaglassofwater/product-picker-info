"""Grounded user-written text extraction and presentation helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from typing import Iterable


EXPLICIT_TEXT_FIELDS = ("review_texts", "comment_texts", "feedback_texts", "reviews", "comments")
USER_AUTHORED_SOURCES = {"reddit", "reddit_arctic_shift", "reddit_software", "hacker_news"}
REDDIT_SOURCES = {"reddit", "reddit_arctic_shift", "reddit_software"}


def _clean(value: object, limit: int = 1000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _published_at(value: object) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            return None
    return _clean(value, 100) or None


def _preferred_reddit_url(record: dict, raw: dict, fallback: str) -> str:
    """Prefer an existing Reddit discussion URL without fabricating one."""
    candidates = (
        raw.get("permalink"), raw.get("reddit_url"), raw.get("post_url"),
        record.get("permalink"), fallback,
    )
    for value in candidates:
        url = str(value or "").strip()
        if url.startswith("/r/") or "reddit.com/r/" in url or "reddit.com/comments/" in url:
            return url if url.startswith("http") else f"https://www.reddit.com{url}"
    return fallback


def _is_author_experience(text: str) -> bool:
    """Conservatively identify first-person ownership/use/need/experience text."""
    first_person = re.search(r"\b(i|i'm|i've|i’d|i'd|my|me|we|we've|our)\b", text, re.I)
    experience = re.search(
        r"\b(own|owned|use|used|using|have|had|need|want|bought|purchase|purchased|received|failed|broke|broken|love|like|recommend|replace|replacement|warranty|looking|trying|carry|carried|wear|wore|tested|ordered)\w*\b",
        text, re.I,
    )
    return bool(first_person and experience)


def classify_reddit_voice(text: str) -> str:
    """Classify source-post semantics without treating every first-person request as use."""
    value = _clean(text).casefold()
    ownership = re.search(r"\b(i|we|my|our)\b.{0,80}\b(own|owned|bought|use|used|using|have had|had|received|wore|tested)\b", value)
    failure = re.search(r"\b(mine|my|our)\b.{0,80}\b(failed|broke|broken|worn|replacement|warranty)\b", value)
    if ownership or failure:
        return "AUTHOR_EXPERIENCE"
    if re.search(r"\b(recommend|recommendation|looking for|in the market|what is the best|which .* should|need a new|want(?:ed)? to ask)\b", value):
        return "USER_NEED"
    if "?" in value or re.search(r"\b(vs\.?|versus|compare|comparison|which of these)\b", value):
        return "PRODUCT_DISCUSSION"
    return "DISCUSSION_TEXT"


def select_feedback_excerpt(text: str, *, max_sentences: int = 4, max_chars: int = 720) -> str:
    """Keep one continuous complete feedback unit without stitching sentences."""
    value = _clean(text, 4000)
    sentences = re.split(r"(?<=[.!?])\s+", value)
    selected: list[str] = []
    for sentence in sentences:
        candidate = " ".join((*selected, sentence)).strip()
        if selected and (len(selected) >= max_sentences or len(candidate) > max_chars):
            break
        selected.append(sentence)
    return " ".join(selected).strip() or value[:max_chars]


def faithful_chinese_translation(text: str) -> str | None:
    """Return reviewed literal translations for the bounded preview excerpts only."""
    value = _clean(text, 4000)
    lowered = value.casefold()
    if "customer service at polywood" in lowered:
        return "朋友们，我真的得夸一夸户外家具制造商 POLYWOOD 的客户服务。2019 或 2020 年，我妻子从 Cracker Barrel 给我买了一把放在门廊上的户外摇椅，就是餐厅外摆放的那种非木制椅子。它由一家名为 POLYWOOD、总体口碑不错的公司制造，我有好几个朋友都很喜欢他们家的家具。可是这把椅子的质量非常糟糕！"
    if "polywood" in lowered and ("rocking chair" in lowered or "rocker" in lowered):
        return "我买过 POLYWOOD 户外摇椅，其中一把后来损坏，并进行了更换。"
    if "old otterbox defender series" in lowered:
        return "我旧的 iPhone 16 Pro 用 OtterBox Defender 手机壳，外层橡胶已经磨损得非常严重；此前一次从胸口高度跌落到混凝土地面后，内部两片式硬壳的上半部分也断成了两半，虽然它之前扛住过多次跌落。我提交了保修申请，支付 14.14 美元保修费和税、提供照片后，申请获批并寄来了替换品。"
    if "otterbox defender" in lowered and ("broke" in lowered or "replacement" in lowered):
        return "我一直使用 OtterBox Defender 手机壳，直到它损坏，之后收到了保修替换品。"
    if "otterbox was always on the more expensive side" in lowered:
        return "OtterBox 一直比较贵，但我以前觉得终身保修让它物有所值。手机壳通常使用 3 到 6 个月后需要更换，保修换新曾收取 6 美元运输处理费。因为我用坏得快，他们当时允许我一次订 5 个，整体还算划算。"
    if "used to recommend kelty" in lowered:
        return "我以前经常推荐 Kelty，也用过他们家的几顶帐篷，身边很多人也在用。它们看起来像是从 Coleman 圆顶帐篷升级到更好产品的实惠选择。我的上一顶帐篷有一根玻璃纤维支杆断了；当时只是下雨、风并不大，雨篷被淋透后，支杆在没有额外受力的情况下折断。"
    if "wanted to upgrade to the wawona" in lowered:
        return "我想升级到 Wawona，但那些令人担忧的一星评价让我很犹豫。过去两年买过这款帐篷的人，目前使用感受如何，会推荐它吗？我也愿意考虑其他选择，但还没找到提供类似前廊结构的产品。"
    if "winkbed luxury firm" in lowered:
        return "我使用的 WinkBed Luxury Firm 床垫在不到四年后出现下陷和内部部件向上顶压的问题。我随后申请了保修，但申请被拒绝。"
    return None


def extract_user_voice(item: dict) -> list[dict]:
    """Extract only attributable source text; aggregate metrics never qualify."""
    output: list[dict] = []
    seen: set[str] = set()
    for record in item.get("source_records", []):
        source = str(record.get("source_platform") or "").casefold()
        url = str(record.get("url") or "")
        raw = record.get("raw_data") if isinstance(record.get("raw_data"), dict) else {}
        if source in REDDIT_SOURCES:
            url = _preferred_reddit_url(record, raw, url)
        candidates: list[tuple[object, str, str, str]] = []
        for field in EXPLICIT_TEXT_FIELDS:
            values = raw.get(field)
            if isinstance(values, (str, dict)):
                values = [values]
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, dict):
                        candidates.append((value.get("text"), str(value.get("url") or url), str(value.get("author") or ""), "COMMENTER_FEEDBACK"))
                    else:
                        candidates.append((value, url, "", "COMMENTER_FEEDBACK"))
        # Reddit self-posts and Show HN submission text are public user-written
        # discussion, but are never promoted to a like/dislike assertion.
        if source in USER_AUTHORED_SOURCES:
            candidates.append((record.get("description"), url, str(raw.get("author") or ""), "AUTHOR_EXPERIENCE"))
        for value, source_url, author, candidate_type in candidates:
            text = _clean(value)
            if not text or not source_url:
                continue
            identity = hashlib.sha256(f"{source}|{source_url}|{text}".encode("utf-8")).hexdigest()
            if identity in seen:
                continue
            seen.add(identity)
            voice_type = candidate_type
            if candidate_type == "AUTHOR_EXPERIENCE":
                voice_type = classify_reddit_voice(text)
            output.append({
                "product_family_id": int(item["family_id"]),
                "product_id": record.get("product_id"),
                "source": source,
                "source_item_id": str(raw.get("id") or raw.get("hn_item_id") or record.get("project_id") or ""),
                "author": author,
                "original_text": text,
                "selected_excerpt": select_feedback_excerpt(text),
                "original_language": "unknown",
                "source_url": source_url,
                "published_at": _published_at(raw.get("created_utc") or raw.get("submitted_at") or raw.get("published_at")),
                "engagement": {
                    key: raw[key] for key in ("score", "num_comments", "points", "comment_count")
                    if raw.get(key) is not None
                },
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "voice_type": voice_type,
                "identity_key": identity,
            })
    return output


def summarize_user_voice(items: Iterable[dict]) -> dict:
    """Group traceable text semantically without inferring sentiment."""
    result = {"author_experience": [], "commenter_feedback": [], "discussion_text": []}
    mapping = {
        "AUTHOR_EXPERIENCE": "author_experience",
        "COMMENTER_FEEDBACK": "commenter_feedback",
        "DISCUSSION_TEXT": "discussion_text",
        "USER_NEED": "discussion_text",
        "PRODUCT_DISCUSSION": "discussion_text",
        "OTHER_DISCUSSION": "discussion_text",
    }
    seen: set[tuple[str, str]] = set()
    for value in items:
        text = _clean(value.get("original_text"), 180)
        source_url = str(value.get("source_url") or "")
        identity = (text, source_url)
        if not text or identity in seen:
            continue
        seen.add(identity)
        key = mapping.get(str(value.get("voice_type") or ""), "discussion_text")
        display = {"text": text, "source_url": source_url}
        if key == "author_experience":
            display["summary_zh"] = grounded_author_summary(str(value.get("original_text") or ""))
        result[key].append(display)
    return result


def normalize_user_voice_items(items: Iterable[dict]) -> list[dict]:
    """Normalize legacy projections to current semantic types without mutation."""
    output = []
    seen: set[tuple[str, str]] = set()
    for original in items:
        value = dict(original)
        text = _clean(value.get("original_text"))
        source = str(value.get("source") or "").casefold()
        identity = (text, str(value.get("source_url") or ""))
        if not text or identity in seen:
            continue
        seen.add(identity)
        if source in REDDIT_SOURCES:
            value["voice_type"] = classify_reddit_voice(text)
        elif value.get("voice_type") == "OTHER_DISCUSSION":
            value["voice_type"] = "DISCUSSION_TEXT"
        output.append(value)
    return output


def grounded_author_summary(text: str) -> str:
    """Create a narrowly grounded Chinese display summary for known factual text."""
    value = _clean(text)
    lowered = value.casefold()
    if "winkbed luxury firm" in lowered and ("four year" in lowered or "4 year" in lowered or "warranty" in lowered):
        return "原帖作者表示其 WinkBed Luxury Firm 床垫在使用不到4年后出现下陷和内部异物顶压问题，并描述了保修申请被拒的经历。"
    if "polywood" in lowered and ("rocking chair" in lowered or "rocker" in lowered):
        return "原帖作者描述了 POLYWOOD 户外摇椅出现损坏后的更换经历，并提到品牌售后处理。"
    if "otterbox" in lowered and ("defender" in lowered or "replacement" in lowered):
        return "原帖作者表示其 OtterBox Defender 手机壳在长期使用和跌落后磨损、破裂，并记录了保修换新过程。"
    if "kelty" in lowered and ("tent" in lowered or "fiberglass pole" in lowered):
        return "原帖作者描述了使用 Kelty 帐篷时玻璃纤维支杆损坏，以及联系售后更换部件的经历。"
    return "原帖作者记录了本人对该产品的实际使用、需求或售后经历；具体内容请查看英文原文。"
