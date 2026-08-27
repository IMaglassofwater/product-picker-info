"""Local Streamlit entry point for the Product Picker dashboard."""

from __future__ import annotations

import math

import streamlit as st

from database_backend import configure_database_environment

# Streamlit Community Cloud stores app secrets in st.secrets. Resolve that
# value before importing dashboard_data/db, whose backend is process-scoped.
configure_database_environment(st.secrets)

from bilingual_display import (
    bilingual_content,
    bilingual_status,
    bilingual_type,
    STATUS_ZH,
    TYPE_ZH,
)
from dashboard_data import (
    AI_STATUSES,
    MANUAL_STATUSES,
    DashboardProduct,
    ProductFilters,
    clear_manual_status,
    enqueue_re_evaluation,
    filter_products,
    load_dashboard_snapshot,
    save_manual_status,
)
from daily_ranker import load_current_opportunities, select_daily_top, select_full_qualified
from product_display import build_product_display, chinese_ai_content
import db


st.set_page_config(page_title="Product Picker", page_icon="🧭", layout="wide")

NAVIGATION_TABS = (
    "🔥 今日机会 / Today",
    "📦 全部产品 / All Products",
    "💻 软件机会 / Software",
    "❤️ 我的收藏 / Favorites",
    "👀 观察列表 / Watchlist",
    "🗑 淘汰库 / Rejected",
)


@st.cache_data(ttl=30, show_spinner=False)
def dashboard_snapshot():
    return load_dashboard_snapshot()


def refresh() -> None:
    dashboard_snapshot.clear()
    st.rerun()


def grouped_meta(product: DashboardProduct) -> tuple[str, str]:
    english = (
        f"Source: {product.source} · Type: {product.display_type.title()} · AI Status: {product.gemini_status}\n\n"
        f"Category: {product.category or 'uncategorized'} · First Seen: {product.first_seen_at[:10] or 'N/A'} · Last Seen: {product.last_seen_at[:10] or 'N/A'}"
    )
    chinese = (
        f"来源：{product.source} · 类型：{TYPE_ZH.get(product.display_type, product.display_type)} · "
        f"AI状态：{STATUS_ZH.get(product.gemini_status, product.gemini_status)}\n\n"
        f"分类：{product.category or 'uncategorized'} · 首次发现：{product.first_seen_at[:10] or 'N/A'} · 最近发现：{product.last_seen_at[:10] or 'N/A'}"
    )
    return english, chinese


def feedback_actions(product: DashboardProduct, key_prefix: str) -> None:
    columns = st.columns(5)
    actions = (
        ("❤️ 感兴趣 / Favorite", "FAVORITE"),
        ("👀 继续观察 / Watch", "WATCH"),
        ("🚫 不感兴趣 / Not Interested", "NOT_INTERESTED"),
    )
    for column, (label, status) in zip(columns[:3], actions):
        if column.button(label, key=f"{key_prefix}-{product.id}-{status}", width="stretch"):
            if save_manual_status(product.id, status):
                st.toast("已保存 · Saved")
                refresh()
    if columns[3].button("🔄 重新评估 / Re-evaluate", key=f"{key_prefix}-{product.id}-reevaluate", width="stretch"):
        if enqueue_re_evaluation(product.id):
            st.toast("已加入重新评估队列 · Added to re-evaluation queue")
            refresh()
    columns[4].link_button("🔗 查看原始来源 / View Original", product.url, width="stretch")
    if product.manual_status and st.button(
        "清除人工状态 · Clear", key=f"{key_prefix}-{product.id}-clear"
    ):
        if clear_manual_status(product.id):
            refresh()


def details(product: DashboardProduct) -> None:
    na = "暂无 · Not available"
    display = build_product_display(product)
    st.markdown("### Product Information · 产品信息")
    st.markdown("**ENGLISH**")
    st.write(f"Title: {product.title}\n\nProduct Summary: {display.product_summary}\n\nDescription: {product.description or 'Description not available.'}\n\nType: {product.display_type.title()} · Category: {product.category}")
    st.markdown("**中文**")
    if display.display_title_zh:
        st.write(f"中文标题：{display.display_title_zh}")
    else:
        st.caption("中文标题待补充 · Chinese title pending")
    if display.product_summary_zh:
        st.write(f"产品梗概：{display.product_summary_zh}")
    else:
        st.caption("中文产品梗概待补充 · Chinese product summary pending")
    st.write(f"类型：{TYPE_ZH.get(product.display_type, product.display_type)} · 分类：{product.category}")
    st.markdown("### Source Evidence · 来源信息")
    st.write(f"Source: {product.source}\n\nURL: {product.url}\n\nFirst Seen: {product.first_seen_at or na} · Last Seen: {product.last_seen_at or na}")
    if display.source_metadata.english:
        st.markdown("**ENGLISH SOURCE DATA**")
        st.write("\n\n".join(f"{label}: {value}" for label, value in display.source_metadata.english))
        st.markdown("**中文来源数据**")
        st.write("\n\n".join(f"{label}：{value}" for label, value in display.source_metadata.chinese))
    st.markdown("### Screening History · 筛选记录")
    st.write(f"Rule: {bilingual_status(product.rule_status)} — {product.rule_reason or na}\n\nFeasibility: {product.feasibility_status or na} — {product.feasibility_reason or na}\n\nCommodity: {bilingual_status(product.commodity_status)} — {product.commodity_reason or na}\n\nSpecificity: {bilingual_status(product.specificity_status)} — {product.specificity_reason or na}")
    if product.gemini_reason or product.gemini_opportunity or product.gemini_risks:
        st.markdown("### AI Opportunity Analysis · AI机会分析")
        render_ai_analysis(product)
    if product.deep_analysis:
        st.markdown("### Deep Analysis")
        st.write(product.deep_analysis)
    if product.software_analysis:
        st.markdown("### Software Analysis")
        st.write(product.software_analysis)
    st.markdown("### Metric History · 指标历史")
    if product.metric_history:
        st.dataframe(product.metric_history, width="stretch", hide_index=True)
    else:
        st.write(na)
    st.markdown(f"**人工反馈 · Feedback:** {product.manual_status or na}")


def render_ai_english(product: DashboardProduct) -> None:
    has_ai = bool(product.gemini_reason or product.gemini_opportunity or product.gemini_risks)
    if not has_ai:
        st.write("AI analysis pending." if product.gemini_status == "AI_PENDING" else "Not analyzed yet.")
        return
    st.write(f"Why It Matters:\n{product.gemini_reason}\n\nOpportunity:\n{product.gemini_opportunity}\n\nMain Risks:\n{'; '.join(product.gemini_risks)}")


def render_ai_chinese(product: DashboardProduct) -> None:
    has_ai = bool(product.gemini_reason or product.gemini_opportunity or product.gemini_risks)
    if not has_ai:
        st.write("AI分析待处理。" if product.gemini_status == "AI_PENDING" else "尚未进入AI机会分析。")
        return
    chinese = chinese_ai_content(
        product.gemini_reason_zh, product.gemini_opportunity_zh, product.gemini_risks_zh
    )
    if chinese.pending:
        st.caption("中文 AI 分析待补充 · Chinese AI analysis pending")
        return
    st.write(f"为什么值得看：\n{chinese.primary_reason or '待补充'}\n\n机会方向：\n{chinese.key_opportunity or '待补充'}\n\n主要风险：\n{'; '.join(chinese.main_risks) if chinese.main_risks else '待补充'}")


def render_ai_analysis(product: DashboardProduct) -> None:
    st.markdown("**ENGLISH**")
    render_ai_english(product)
    st.markdown("**中文**")
    render_ai_chinese(product)


def product_card(product: DashboardProduct, key_prefix: str, *, final_score: int | None = None, compact: bool = True) -> None:
    with st.container(border=True):
        display = build_product_display(product)
        title_col, score_col = st.columns([5, 1])
        title_col.subheader(display.display_title_zh or display.display_title)
        if not display.display_title_zh:
            title_col.caption("中文标题待补充 · Chinese title pending")
        else:
            title_col.caption(f"English Original: {display.display_title}")
        if final_score is not None:
            score_col.metric("Final Score", final_score)
        english_meta, chinese_meta = grouped_meta(product)
        st.markdown("**ENGLISH**")
        st.caption(english_meta)
        st.markdown(f"**Product Summary:**  \n{display.product_summary}")
        if not compact:
            st.markdown("### AI Opportunity Analysis")
            render_ai_english(product)
        st.markdown("**中文**")
        st.caption(chinese_meta)
        if display.product_summary_zh:
            st.markdown(f"**产品梗概：**  \n{display.product_summary_zh}")
        else:
            st.caption("中文产品梗概待补充 · Chinese product summary pending")
        if not compact:
            st.markdown("### AI机会分析")
            render_ai_chinese(product)
        has_ai = bool(product.gemini_reason or product.gemini_opportunity or product.gemini_risks)
        if compact and has_ai:
            with st.expander("AI Opportunity Analysis · AI机会分析"):
                render_ai_analysis(product)
        elif compact:
            st.caption("AI analysis pending · AI分析待处理" if product.gemini_status == "AI_PENDING" else "Not analyzed yet · 尚未进入AI机会分析")
        if product.rejected:
            reason = product.commodity_reason or product.specificity_reason or product.feasibility_reason or product.rule_reason or product.gemini_reason
            st.warning(f"**未进入推荐原因 · Why It Was Filtered Out:** {reason or '暂无 · Not available'}")
        feedback_actions(product, key_prefix)
        with st.expander("查看详情 · View Details"):
            details(product)


def filter_controls(products: list[DashboardProduct], prefix: str) -> ProductFilters:
    keyword = st.text_input("🔎 搜索产品 / Search products", key=f"{prefix}-keyword")
    c1, c2, c3 = st.columns(3)
    sources = tuple(c1.multiselect("来源 · Source", sorted({p.source for p in products}), key=f"{prefix}-sources"))
    date_range = c2.selectbox(
        "日期 · Date", ("all", "today", "7d", "30d"),
        format_func=lambda x: {"all": "全部 · All", "today": "今天 · Today", "7d": "过去7天", "30d": "过去30天"}[x],
        key=f"{prefix}-date",
    )
    types = tuple(c3.multiselect("类型 · Type", ("physical", "software", "inspiration"), key=f"{prefix}-types"))
    c4, c5, c6 = st.columns(3)
    rule = tuple(c4.multiselect("Rule状态", sorted({p.rule_status for p in products if p.rule_status}), key=f"{prefix}-rule"))
    feasibility = tuple(c5.multiselect("Feasibility状态", sorted({p.feasibility_status for p in products if p.feasibility_status}), key=f"{prefix}-feasibility"))
    commodity = tuple(c6.multiselect("Commodity状态", sorted({p.commodity_status for p in products if p.commodity_status}), key=f"{prefix}-commodity"))
    c7, c8, c9 = st.columns(3)
    specificity = tuple(c7.multiselect("Specificity状态", sorted({p.specificity_status for p in products if p.specificity_status}), key=f"{prefix}-specificity"))
    gemini = tuple(c8.multiselect("Gemini状态", AI_STATUSES, key=f"{prefix}-gemini"))
    manual = tuple(c9.multiselect("人工状态 · Manual", MANUAL_STATUSES, key=f"{prefix}-manual"))
    return ProductFilters(keyword, sources, date_range, types, rule, feasibility, commodity, specificity, gemini, manual)


def paginated_cards(products: list[DashboardProduct], prefix: str, page_size: int = 50) -> None:
    pages = max(1, math.ceil(len(products) / page_size))
    state_key = f"{prefix}-page-number"
    st.session_state[state_key] = min(max(1, st.session_state.get(state_key, 1)), pages)
    previous, indicator, following = st.columns([1, 2, 1])
    if previous.button("← 上一页 / Previous", key=f"{prefix}-previous", disabled=st.session_state[state_key] <= 1, width="stretch"):
        st.session_state[state_key] -= 1
        st.rerun()
    if following.button("下一页 / Next →", key=f"{prefix}-next", disabled=st.session_state[state_key] >= pages, width="stretch"):
        st.session_state[state_key] += 1
        st.rerun()
    page = st.session_state[state_key]
    start = (int(page) - 1) * page_size
    end = min(start + page_size, len(products))
    indicator.markdown(f"**显示 · Showing {start + 1 if products else 0}–{end} / {len(products)}**")
    for product in products[start:start + page_size]:
        product_card(product, prefix)


def today_page(snapshot) -> None:
    st.header("今日机会 · Today's Opportunities")
    opportunities = load_current_opportunities()
    ranking = select_daily_top(opportunities)
    qualified = select_full_qualified(opportunities)
    by_url = {product.url: product for product in snapshot.products}
    fetched = sum(row["fetched"] for row in snapshot.pipeline_sources)
    metrics = st.columns(3)
    metrics[0].metric("今日抓取 · Fetched", fetched)
    metrics[1].metric("符合基本要求 · Qualified", len(qualified))
    metrics[2].metric("AI待分析 · AI Pending", sum(item.triage is None for item in opportunities))
    st.info(f"数据库总记录 · Database records: {len(snapshot.products)}。点击上方“📦 全部产品 / All Products”浏览完整历史。")
    st.subheader("数据源状态 · Source Status")
    if snapshot.pipeline_sources:
        status_rows = []
        for row in snapshot.pipeline_sources:
            status_rows.append({
                "Source": row["source_platform"], "Status": "⚠" if row["failed"] else "✓",
                "Fetched": row["fetched"], "New": row["new_count"], "Updated": row["updated_count"],
                "Last Run": row["run"].get("finished_at") or row["run"].get("started_at"),
            })
        st.dataframe(status_rows, width="stretch", hide_index=True)
    else:
        st.info("暂无运行记录 · No pipeline run available")
    st.header("今日优先关注 · Today's Top Picks")
    for item in ranking.final[:10]:
        product = by_url.get(item.candidate.source_url)
        if product:
            product_card(product, "today-top", final_score=item.final_rank_score, compact=False)
    top_ids = {item.candidate.candidate_id for item in ranking.final[:10]}
    st.header("更多符合要求的机会 · More Qualified Opportunities")
    for item in qualified:
        if item.candidate.candidate_id in top_ids:
            continue
        product = by_url.get(item.candidate.source_url)
        if product:
            product_card(product, "today-more", final_score=item.final_rank_score, compact=False)


def all_products_page(snapshot) -> None:
    st.header("全部历史产品 · All Historical Products")
    st.metric("数据库记录 · Database Records", len(snapshot.products))
    keyword = st.text_input("🔎 搜索产品 / Search products", key="all-keyword")
    c1, c2, c3 = st.columns(3)
    source = c1.selectbox("来源 / Source", ("全部 · All",) + tuple(sorted({p.source for p in snapshot.products})))
    date_value = c2.selectbox("时间 / Date", ("全部历史 · All", "今天 · Today", "7天 · 7 Days", "30天 · 30 Days"))
    type_value = c3.selectbox("产品类型 / Type", ("全部 · All", "实体商品 · Physical", "软件 · Software", "设计/灵感 · Design/Inspiration"))
    c4, c5, c6 = st.columns(3)
    ai_value = c4.selectbox("AI状态 / AI Status", ("全部 · All", "通过 · PASS", "待复核 · REVIEW", "未通过 · REJECT", "AI待分析 · AI Pending", "未进入AI分析 · Not Analyzed"))
    rule_value = c5.selectbox("规则状态 / Filter Status", ("全部 · All", "候选 · Candidate", "待复核 · Review", "已过滤 · Rejected", "成熟普通商品 · Commodity", "范围过宽 · Too Broad"))
    manual_value = c6.selectbox("人工状态 / My Status", ("全部 · All", "感兴趣 · Favorite", "继续观察 · Watch", "不感兴趣 · Not Interested", "重新评估 · Re-evaluate"))
    filters = ProductFilters(
        keyword=keyword,
        sources=() if source.startswith("全部") else (source,),
        date_range={"今天 · Today":"today", "7天 · 7 Days":"7d", "30天 · 30 Days":"30d"}.get(date_value, "all"),
        product_types={"实体商品 · Physical":("physical",), "软件 · Software":("software",), "设计/灵感 · Design/Inspiration":("inspiration",)}.get(type_value, ()),
        gemini_statuses={"通过 · PASS":("PASS",), "待复核 · REVIEW":("REVIEW",), "未通过 · REJECT":("REJECT",), "AI待分析 · AI Pending":("AI_PENDING",), "未进入AI分析 · Not Analyzed":("NOT_ANALYZED",)}.get(ai_value, ()),
        rule_statuses={"候选 · Candidate":("candidate",), "待复核 · Review":("uncertain",), "已过滤 · Rejected":("rejected",)}.get(rule_value, ()),
        commodity_statuses=("COMMODITY",) if rule_value.startswith("成熟") else (),
        specificity_statuses=("TOO_BROAD",) if rule_value.startswith("范围") else (),
        manual_statuses={"感兴趣 · Favorite":("FAVORITE",), "继续观察 · Watch":("WATCH",), "不感兴趣 · Not Interested":("NOT_INTERESTED",)}.get(manual_value, ()),
    )
    products = filter_products(snapshot.products, filters)
    if manual_value.startswith("重新"):
        queued = {row["entity_id"] for row in snapshot.re_evaluation_queue if row["entity_type"] == "product"}
        products = [product for product in products if str(product.id) in queued]
    st.metric("当前筛选结果 · Current Results", len(products))
    paginated_cards(products, "all-results", 50)


def software_page(snapshot) -> None:
    st.header("软件机会 · Software Opportunities")
    software = [product for product in snapshot.products if product.display_type == "software"]
    gemini = tuple(st.multiselect("AI状态 · AI Status", AI_STATUSES, key="software-ai"))
    keyword = st.text_input("搜索 · Search", key="software-search")
    paginated_cards(filter_products(software, ProductFilters(keyword=keyword, gemini_statuses=gemini)), "software")


def manual_page(snapshot, status: str, title: str, prefix: str) -> None:
    st.header(title)
    keyword = st.text_input("搜索 · Search", key=f"{prefix}-search")
    products = filter_products(snapshot.products, ProductFilters(keyword=keyword, manual_statuses=(status,)))
    paginated_cards(products, prefix)


def rejected_page(snapshot) -> None:
    st.header("淘汰库 · Filtered & Rejected Archive")
    st.info("这些产品没有进入当前推荐，但历史数据仍然保留。你可以随时搜索、收藏或重新评估。\n\nThese products were filtered out of current recommendations, but remain available for review.")
    with st.expander(f"待重新评估 · Re-evaluation Queue ({len(snapshot.re_evaluation_queue)})"):
        st.dataframe(snapshot.re_evaluation_queue, width="stretch", hide_index=True)
    keyword = st.text_input("搜索 · Search", key="rejected-search")
    products = filter_products(snapshot.products, ProductFilters(keyword=keyword, rejected_only=True))
    paginated_cards(products, "rejected")


snapshot = dashboard_snapshot()
st.title("Product Picker")
database_columns = st.columns(3)
database_columns[0].metric(
    "数据库 / Database",
    "PostgreSQL" if db.DATABASE_SETTINGS.backend == "postgresql" else "SQLite",
)
database_columns[1].metric("连接状态 / Connection", "Connected")
database_columns[2].metric("产品记录 / Products", len(snapshot.products))
tabs = st.tabs(NAVIGATION_TABS)
with tabs[0]:
    today_page(snapshot)
with tabs[1]:
    all_products_page(snapshot)
with tabs[2]:
    software_page(snapshot)
with tabs[3]:
    manual_page(snapshot, "FAVORITE", "我的收藏 · Favorites", "favorites")
with tabs[4]:
    manual_page(snapshot, "WATCH", "观察列表 · Watchlist", "watchlist")
with tabs[5]:
    rejected_page(snapshot)
