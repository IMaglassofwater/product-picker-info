"""Local, compact Daily Opportunity Report generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from html import escape
from pathlib import Path
from typing import Literal

from daily_ranker import DailyRankingResult, RankedOpportunity


ResearchStatus = Literal["TRIAGED", "DEEP_ANALYZED", "DEEP_ANALYSIS_FAILED"]


@dataclass(frozen=True)
class DailyReportItem:
    rank: int
    candidate_id: str
    display_title: str
    candidate_type: str
    opportunity_type: str
    source: str
    theme: str
    final_rank_score: int
    triage_score: int | None
    why_it_matters: str
    why_it_matters_zh: str
    key_opportunity: str
    key_opportunity_zh: str
    main_risks: list[str]
    main_risks_zh: str
    research_status: ResearchStatus
    source_url: str
    deep_score: int | None = None
    recommended_next_step: str = "DEEP_RESEARCH_OPTIONAL"


@dataclass(frozen=True)
class DailyReport:
    report_date: str
    items: list[DailyReportItem] = field(default_factory=list)
    top_picks: list[DailyReportItem] = field(default_factory=list)

    @property
    def physical_count(self) -> int:
        return sum(item.opportunity_type == "Physical" for item in self.items)

    @property
    def software_count(self) -> int:
        return sum(item.opportunity_type == "Software" for item in self.items)


def _compact(text: str, limit: int = 320) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


_ZH_TITLES = {
    "Fanny pack without zipper": "无拉链快速取物腰包",
    "PaperRepublic alternative / DIY leather journal": "轻薄袖珍皮革手账替代方案",
    "Looking for key organiser": "兼容不同钥匙形状的钥匙收纳器",
    "Recommendation for a sleeping bag that must be stored compressed?": "适合长期压缩存放的睡袋方案",
    "Review of Osprey Ultralight Dry Stuff Pack 20L": "20L 超轻防水收纳背包改进机会",
    "First one bagging trip coming up": "轻量模块化旅行收纳机会",
}


def _chinese_summary(candidate_type: str, opportunity_type: str) -> tuple[str, str, str]:
    if opportunity_type == "Software":
        return (
            "现有记录描述了一个软件用户问题，并已通过当前基础质量门槛。",
            "围绕英文摘要中的核心问题验证一个轻量 MVP。",
            "真实需求、实现依赖和竞争情况仍需验证。",
        )
    if candidate_type == "consumer_trend":
        return (
            "该消费趋势记录已通过当前免费筛选，具体市场强度仍需验证。",
            "围绕英文机会描述中的产品结构或使用体验进行小范围验证。",
            "趋势持续性、竞争和供应链仍需验证。",
        )
    if candidate_type == "inspiration_product":
        return (
            "该设计内容提供了一个可继续验证的实体产品灵感。",
            "评估该创意能否转化为低复杂度的小型消费品改款。",
            "需求证据、制造可行性和成本仍需验证。",
        )
    if candidate_type == "validated_product":
        return (
            "现有记录描述了一个实体产品及可继续研究的改进方向。",
            "围绕英文摘要中的具体使用问题验证小改款机会。",
            "需求强度、差异化和供应链仍需验证。",
        )
    return (
        "现有记录包含一个明确用户需求，并已通过当前基础质量门槛。",
        "围绕英文机会描述中的具体功能缺口进行进一步验证。",
        "需求规模、竞争和供应链仍需验证。",
    )


def _report_item(
    ranked: RankedOpportunity, failed_candidate_ids: set[str]
) -> DailyReportItem:
    candidate = ranked.candidate
    triage = candidate.triage
    physical = candidate.physical_analysis if ranked.analysis_source == "Physical Deep Analysis" else None
    software = candidate.software_analysis if ranked.analysis_source == "Software Analysis" else None
    analysis = software or physical

    if analysis:
        research_status: ResearchStatus = "DEEP_ANALYZED"
    elif candidate.candidate_id in failed_candidate_ids or (
        candidate.physical_analysis is not None and ranked.analysis_source != "Physical Deep Analysis"
    ):
        research_status = "DEEP_ANALYSIS_FAILED"
    else:
        research_status = "TRIAGED"

    if physical:
        why = physical.opportunity_summary
        key = physical.micro_innovation_ideas[0] if physical.micro_innovation_ideas else physical.existing_solution_gap
        risks = physical.biggest_risks
        deep_score = physical.deep_score
        next_step = physical.recommended_next_step
    elif software:
        why = software.opportunity_summary
        key = software.mvp_idea[0] if software.mvp_idea else software.existing_solution_gap
        risks = software.biggest_risks
        deep_score = software.software_score
        next_step = software.recommended_next_step
    else:
        why = triage.primary_reason if triage else "Current candidate evidence passed the offline ranking gates."
        key = triage.key_opportunity if triage else "Further validation is optional."
        risks = triage.main_risks if triage else ["Further validation is required."]
        deep_score = None
        next_step = "DEEP_RESEARCH_OPTIONAL"

    why_zh, key_zh, risks_zh = _chinese_summary(
        candidate.candidate_type, candidate.opportunity_type
    )

    return DailyReportItem(
        rank=ranked.rank or 0,
        candidate_id=candidate.candidate_id,
        display_title=candidate.display_title,
        candidate_type=candidate.candidate_type,
        opportunity_type=candidate.opportunity_type,
        source=candidate.source_platform,
        theme=candidate.theme,
        final_rank_score=ranked.final_rank_score,
        triage_score=triage.triage_score if triage else None,
        why_it_matters=_compact(why),
        why_it_matters_zh=why_zh,
        key_opportunity=_compact(key),
        key_opportunity_zh=key_zh,
        main_risks=[_compact(risk, 180) for risk in risks[:3]],
        main_risks_zh=risks_zh,
        research_status=research_status,
        source_url=candidate.source_url,
        deep_score=deep_score,
        recommended_next_step=next_step,
    )


def build_daily_report(
    ranking: DailyRankingResult,
    *,
    qualified: list[RankedOpportunity] | None = None,
    report_date: str | None = None,
    failed_candidate_ids: set[str] | None = None,
) -> DailyReport:
    """Build at most ten display-only items from an already filtered ranking."""
    failed = failed_candidate_ids or set()
    all_ranked = qualified if qualified is not None else ranking.final
    all_items = [_report_item(item, failed) for item in all_ranked]
    by_id = {item.candidate_id: item for item in all_items}
    return DailyReport(
        report_date=report_date or date.today().isoformat(),
        items=all_items,
        top_picks=[by_id[item.candidate.candidate_id] for item in ranking.final[:10]
                   if item.candidate.candidate_id in by_id],
    )


def render_daily_report_html(report: DailyReport) -> str:
    """Render standalone mobile-readable HTML without scripts or external assets."""
    def friendly_source(source: str) -> str:
        value = source.casefold()
        if "reddit" in value:
            return "Reddit"
        if value == "amazon":
            return "Amazon"
        if "yanko" in value:
            return "Yanko Design"
        if "product_hunt" in value:
            return "Product Hunt"
        if "kickstarter" in value or "ksinsights" in value:
            return "Kickstarter"
        if "indiegogo" in value:
            return "Indiegogo"
        return source

    status_label = {
        "TRIAGED": "值得进一步研究 · Worth Further Review",
        "DEEP_ANALYZED": "已深度分析 · Deep Analysis Available",
        "DEEP_ANALYSIS_FAILED": "可进一步深挖 · Further Research Available",
    }

    def card(item: DailyReportItem) -> str:
        risks = "；".join(item.main_risks) or "仍需验证"
        type_label = "Software Opportunity" if item.opportunity_type == "Software" else item.candidate_type
        zh_title = _ZH_TITLES.get(item.display_title)
        title = (f"<h2>{escape(zh_title)}</h2><div class=\"original\">{escape(item.display_title)}</div>"
                 if zh_title else f"<h2>{escape(item.display_title)}</h2>")
        return f"""<article class=\"card\">
<div class=\"card-head\"><span class=\"rank\">#{item.rank}</span><span class=\"score\">{item.final_rank_score} / 100</span></div>
{title}
<div class=\"meta\">来源 Source：{escape(friendly_source(item.source))} · 类型 Type：{escape(type_label)} · 主题 Theme：{escape(item.theme)}</div>
<h3>为什么值得看 · Why It Matters</h3><p><b>中文：</b>{escape(item.why_it_matters_zh)}</p><p><b>English:</b> {escape(item.why_it_matters)}</p>
<h3>机会方向 · Opportunity</h3><p><b>中文：</b>{escape(item.key_opportunity_zh)}</p><p><b>English:</b> {escape(item.key_opportunity)}</p>
<h3>主要风险 · Main Risks</h3><p class=\"risk\"><b>中文：</b>{escape(item.main_risks_zh)}</p><p class=\"risk\"><b>English:</b> {escape(risks)}</p>
<h3>下一步 · Next Step</h3><p>{escape(item.recommended_next_step)}</p>
<div class=\"footer\"><span>{status_label[item.research_status]}</span><a target=\"_blank\" rel=\"noopener noreferrer\" href=\"{escape(item.source_url, quote=True)}\">查看原始来源 · View Original Source</a></div>
</article>"""

    top_ids = {item.candidate_id for item in report.top_picks}
    more_physical = [item for item in report.items
                     if item.candidate_id not in top_ids
                     and item.opportunity_type == "Physical"
                     and item.candidate_type not in {"inspiration_product", "consumer_trend"}]
    software = [item for item in report.items if item.opportunity_type == "Software"]
    inspiration = [item for item in report.items
                   if item.candidate_type in {"inspiration_product", "consumer_trend"}]
    source_counts: dict[str, int] = {}
    for item in report.items:
        name = friendly_source(item.source)
        source_counts[name] = source_counts.get(name, 0) + 1
    source_summary = " · ".join(f"{escape(name)} {count}" for name, count in source_counts.items()) or "None"
    software_html = "".join(card(item) for item in software) or "<p class=\"empty\">今日没有达到标准的软件机会<br>No software opportunities met today's quality threshold.</p>"
    more_html = "".join(card(item) for item in more_physical) or "<p class=\"empty\">没有其他合格实体机会 · No additional qualified physical opportunities.</p>"
    inspiration_html = "".join(card(item) for item in inspiration) or "<p class=\"empty\">今日没有达到标准的设计或趋势灵感 · No design or trend inspiration met today's threshold.</p>"
    direct_physical = sum(item.opportunity_type == "Physical" for item in report.items)
    return f"""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Product Picker Daily</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f5f7fa;color:#172033;font-family:system-ui,-apple-system,Segoe UI,sans-serif;line-height:1.55}}main{{max-width:820px;margin:auto;padding:28px 16px 48px}}header{{margin-bottom:22px}}h1{{margin:0;font-size:30px}}section{{margin:30px 0}}section>h2{{font-size:24px}}.sub,.original{{color:#667085;margin:6px 0}}.summary{{background:#eef3ff;border-radius:12px;padding:14px;margin-top:14px}}.card{{background:#fff;border:1px solid #e4e7ec;border-radius:14px;padding:20px;margin:14px 0;box-shadow:0 3px 12px rgba(16,24,40,.05)}}.card-head,.footer{{display:flex;align-items:center;justify-content:space-between;gap:12px}}.rank{{font-weight:800;color:#3157d5}}.score{{font-size:21px;font-weight:800}}.card h2{{font-size:20px;margin:10px 0 0}}h3{{font-size:13px;color:#667085;margin:15px 0 3px;text-transform:uppercase;letter-spacing:.04em}}p{{margin:2px 0}}.meta,.risk,.empty{{color:#667085}}.footer{{border-top:1px solid #eef0f3;margin-top:18px;padding-top:13px}}a{{color:#3157d5;text-decoration:none;font-weight:650}}@media(max-width:520px){{h1{{font-size:25px}}.card{{padding:16px}}.footer{{align-items:flex-start;flex-direction:column}}}}
</style></head><body><main><header><h1>Product Picker Daily<br><span class=\"sub\">产品机会日报</span></h1><p class=\"sub\">{escape(report.report_date)}</p><div class=\"summary\">今日值得查看 Qualified: {len(report.items)} · 实体 Physical: {direct_physical} · 软件 Software: {len(software)} · 设计/趋势 Inspiration: {len(inspiration)}<br>来源分布 Source Distribution: {source_summary}</div></header>
<section><h2>今日优先关注<br><span class=\"sub\">Today's Top Picks</span></h2>{''.join(card(item) for item in report.top_picks)}</section>
<section><h2>更多值得查看的实体机会<br><span class=\"sub\">More Qualified Physical Opportunities</span></h2>{more_html}</section>
<section><h2>轻量软件机会<br><span class=\"sub\">Software Opportunities</span></h2>{software_html}</section>
<section><h2>设计与趋势灵感<br><span class=\"sub\">Design &amp; Trend Inspiration</span></h2>{inspiration_html}</section>
</main></body></html>"""


def write_daily_report_html(report: DailyReport, directory: Path | str = "reports") -> Path:
    output_dir = Path(directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{report.report_date}-product-picker.html"
    path.write_text(render_daily_report_html(report), encoding="utf-8")
    return path
