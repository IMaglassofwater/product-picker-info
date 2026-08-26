"""Deterministic bilingual display helpers; no translation API is used."""

from __future__ import annotations

from dataclasses import dataclass


CHINESE_UNAVAILABLE = "暂未生成中文摘要"
CHINESE_TITLE_UNAVAILABLE = "暂无中文标题"

ZH_TITLES = {
    "Fanny pack without zipper": "无拉链快速取物腰包",
    "PaperRepublic alternative / DIY leather journal": "轻薄袖珍皮革手账替代方案",
    "Looking for key organiser": "兼容不同钥匙形状的钥匙收纳器",
    "Recommendation for a sleeping bag that must be stored compressed?": "适合长期压缩存放的睡袋方案",
    "Review of Osprey Ultralight Dry Stuff Pack 20L": "20L超轻防水收纳背包改进机会",
    "First one bagging trip coming up": "轻量模块化旅行收纳机会",
}

STATUS_LABELS = {
    "PASS": "通过 · PASS",
    "REVIEW": "待复核 · REVIEW",
    "REJECT": "未通过 · REJECT",
    "AI_PENDING": "AI待分析 · AI Pending",
    "NOT_ANALYZED": "未进入AI分析 · Not Analyzed",
    "FAVORITE": "感兴趣 · Favorite",
    "WATCH": "继续观察 · Watch",
    "NOT_INTERESTED": "不感兴趣 · Not Interested",
    "candidate": "候选 · Candidate",
    "uncertain": "待复核 · Review",
    "rejected": "已过滤 · Rejected",
    "COMMODITY": "成熟普通商品 · Commodity",
    "TOO_BROAD": "范围过宽 · Too Broad",
}

TYPE_LABELS = {
    "physical": "实体商品 · Physical",
    "software": "软件 · Software",
    "inspiration": "设计/灵感 · Design/Inspiration",
}

TYPE_ZH = {"physical": "实体商品", "software": "软件机会", "inspiration": "设计灵感"}
STATUS_ZH = {
    "PASS": "通过", "REVIEW": "待复核", "REJECT": "淘汰",
    "AI_PENDING": "AI待分析", "NOT_ANALYZED": "未进入AI分析",
}


def chinese_title(original: str) -> str:
    return ZH_TITLES.get(original, CHINESE_TITLE_UNAVAILABLE)


def preferred_title(original: str, display_title_zh: str | None = None) -> str:
    """Prefer persisted AI Chinese, then a known mapping, then the original."""
    return (display_title_zh or "").strip() or ZH_TITLES.get(original, original)


def bilingual_status(value: str) -> str:
    return STATUS_LABELS.get(value, value or "暂无 · Not available")


def bilingual_type(value: str) -> str:
    return TYPE_LABELS.get(value, value or "暂无 · Not available")


def chinese_dynamic_text(_english: str, chinese: str | None = None) -> str:
    """Prefer persisted Chinese and otherwise return a compact honest fallback."""
    return (chinese or "").strip() or "待补充"


@dataclass(frozen=True)
class BilingualContent:
    primary: str
    english_comparison: str
    chinese_pending: bool


def bilingual_content(english: str | None, chinese: str | None) -> BilingualContent:
    """Show Chinese first when available; otherwise make English the main text."""
    english_text = (english or "").strip() or "Not available"
    chinese_text = (chinese or "").strip()
    if chinese_text:
        return BilingualContent(chinese_text, english_text, False)
    return BilingualContent(english_text, "", True)




future_bilingual_ai_output = "planned"
