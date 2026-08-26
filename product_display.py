"""Pure presentation helpers for product information and source evidence."""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re
from typing import Any

from bilingual_display import preferred_title


SUMMARY_LIMIT = 420
DESCRIPTION_FIELDS = (
    "tagline", "excerpt", "description", "short_description",
    "shortDescription", "content", "summary",
)


@dataclass(frozen=True)
class SourceMetadata:
    english: tuple[tuple[str, str], ...]
    chinese: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ProductDisplay:
    display_title: str
    display_title_zh: str
    product_summary: str
    product_summary_zh: str
    source_metadata: SourceMetadata
    ai_display_status: str


@dataclass(frozen=True)
class ChineseAIContent:
    primary_reason: str
    key_opportunity: str
    main_risks: tuple[str, ...]
    pending: bool


def chinese_ai_content(
    primary_reason_zh: str | None,
    key_opportunity_zh: str | None,
    main_risks_zh: list[str] | tuple[str, ...] | None,
) -> ChineseAIContent:
    """Return only persisted Chinese AI content; never synthesize analysis."""
    reason = (primary_reason_zh or "").strip()
    opportunity = (key_opportunity_zh or "").strip()
    risks = tuple(str(item).strip() for item in (main_risks_zh or ()) if str(item).strip())
    return ChineseAIContent(reason, opportunity, risks, not any((reason, opportunity, risks)))


def _clean(value: Any, limit: int = SUMMARY_LIMIT) -> str:
    if value is None:
        return ""
    text = re.sub(r"<[^>]+>", " ", unescape(str(value)))
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def product_summary(description: str | None, raw_data: dict[str, Any], title: str) -> str:
    """Select, clean, and safely truncate source text without rewriting it."""
    candidates = [description]
    candidates.extend(raw_data.get(field) for field in DESCRIPTION_FIELDS)
    candidates.append(title)
    return next((cleaned for value in candidates if (cleaned := _clean(value))), "Description not available.")


def product_summary_zh(raw_data: dict[str, Any]) -> str:
    for field in ("summary_zh", "description_zh", "tagline_zh", "excerpt_zh"):
        if cleaned := _clean(raw_data.get(field)):
            return cleaned
    return ""


def ai_display_status(candidate_id: str, has_ai_result: bool) -> str:
    if has_ai_result:
        return "ANALYZED"
    return "AI_PENDING" if candidate_id else "NOT_ANALYZED"


def _value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _format(value: Any, suffix: str = "") -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        text = f"{value:,.2f}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    return f"{text}{suffix}"


def extract_source_metadata(source: str, raw: dict[str, Any]) -> SourceMetadata:
    """Allow-list truthful public metadata for each supported source."""
    fields: list[tuple[str, str, tuple[str, ...], str]] = []
    if source in {"reddit", "reddit_arctic_shift"}:
        fields = [
            ("Subreddit", "社区", ("subreddit",), ""),
            ("Score", "评分", ("score",), ""),
            ("Comments", "评论数", ("num_comments", "comments"), ""),
            ("Excerpt", "摘录", ("excerpt", "selftext"), ""),
        ]
    elif source == "amazon":
        fields = [
            ("Price", "价格", ("price",), ""), ("Rating", "评分", ("rating",), ""),
            ("Reviews", "评论数", ("review_count",), ""), ("Rank", "排名", ("rank",), ""),
            ("Rank Change", "排名变化", ("rank_change",), ""),
        ]
    elif source == "kickstarter":
        fields = [
            ("Funding", "筹资金额", ("pledged",), ""), ("Goal", "目标金额", ("goal",), ""),
            ("Funded", "完成比例", ("percent_funded", "funding_percentage"), "%"),
            ("Backers", "支持者", ("backers_count", "backers"), ""),
            ("Status", "状态", ("state", "campaign_status"), ""),
        ]
    elif source == "indiegogo":
        fields = [
            ("Funding", "筹资金额", ("funds_gathered", "pledged"), ""),
            ("Goal", "目标金额", ("campaign_goal", "goal"), ""),
            ("Funded", "完成比例", ("funding_percentage", "percent_funded"), "%"),
            ("Backers", "支持者", ("backer_count", "backers_count"), ""),
            ("Status", "状态", ("campaign_status", "state"), ""),
        ]
    elif source == "product_hunt":
        fields = [
            ("Tagline", "标语", ("tagline", "content"), ""),
            ("Topics", "主题", ("topics", "category"), ""),
            ("Votes", "投票数", ("votes", "votes_count"), ""),
        ]
    elif source == "yanko_design":
        fields = [
            ("Category", "分类", ("categories", "category"), ""),
            ("Excerpt", "摘录", ("excerpt", "description"), ""),
            ("Published", "发布日期", ("published_at", "published"), ""),
        ]
    english: list[tuple[str, str]] = []
    chinese: list[tuple[str, str]] = []
    for en_label, zh_label, keys, suffix in fields:
        value = _value(raw, *keys)
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        rendered = _clean(_format(value, suffix), 240)
        if rendered:
            english.append((en_label, rendered))
            chinese.append((zh_label, rendered))
    return SourceMetadata(tuple(english), tuple(chinese))


def build_product_display(product) -> ProductDisplay:
    raw_value = getattr(product, "raw_data", {})
    raw = raw_value if isinstance(raw_value, dict) else {}
    zh_title = (getattr(product, "display_title_zh", "") or "").strip()
    resolved = preferred_title(product.title, zh_title)
    mapped_zh = resolved if resolved != product.title else ""
    return ProductDisplay(
        display_title=product.title,
        display_title_zh=mapped_zh,
        product_summary=getattr(product, "product_summary", "") or product_summary(product.description, raw, product.title),
        product_summary_zh=getattr(product, "product_summary_zh", "") or product_summary_zh(raw),
        source_metadata=getattr(product, "source_metadata", None) or extract_source_metadata(product.source_platform, raw),
        ai_display_status=ai_display_status(
            getattr(product, "candidate_id", ""), bool(getattr(product, "gemini_reason", "")),
        ),
    )
