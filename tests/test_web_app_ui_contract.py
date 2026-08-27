from pathlib import Path

from bilingual_display import (
    CHINESE_UNAVAILABLE,
    bilingual_status,
    chinese_title,
)
from dashboard_data import ProductFilters, filter_products, load_dashboard_snapshot


APP_SOURCE = Path("app.py").read_text(encoding="utf-8")


def test_six_visible_top_navigation_pages_are_defined():
    labels = (
        "🔥 今日机会 / Today", "📦 全部产品 / All Products",
        "💻 软件机会 / Software", "❤️ 我的收藏 / Favorites",
        "👀 观察列表 / Watchlist", "🗑 淘汰库 / Rejected",
    )
    assert "selected_page = st.radio" in APP_SOURCE
    assert "horizontal=True" in APP_SOURCE
    assert all(label in APP_SOURCE for label in labels)
    assert "st.sidebar.radio" not in APP_SOURCE


def test_all_products_ui_contract_is_visible_and_not_qualified_only():
    required = (
        "全部历史产品 · All Historical Products",
        "🔎 搜索产品 / Search products",
        "来源 / Source", "时间 / Date", "产品类型 / Type",
        "AI状态 / AI Status", "规则状态 / Filter Status",
        "人工状态 / My Status",
    )
    assert all(label in APP_SOURCE for label in required)
    assert "filter_products(snapshot.products, filters)" in APP_SOURCE


def test_runtime_all_products_and_real_search_smoke():
    snapshot = load_dashboard_snapshot()
    assert len(snapshot.products) == 653
    assert len(filter_products(snapshot.products, ProductFilters(keyword="bathroom"))) >= 1
    assert len(filter_products(snapshot.products, ProductFilters(keyword="backpack"))) > 1


def test_bilingual_card_and_rejected_copy_contract():
    required = (
        "English Original:", "AI Opportunity Analysis · AI机会分析",
        "Why It Matters:", "Opportunity:", "Main Risks:",
        "Product Summary", "Source Evidence · 来源信息",
        "这些产品没有进入当前推荐", "These products were filtered out",
        "❤️ 感兴趣 / Favorite", "👀 继续观察 / Watch",
        "🚫 不感兴趣 / Not Interested", "🔄 重新评估 / Re-evaluate",
        "🔗 查看原始来源 / View Original",
    )
    assert all(text in APP_SOURCE for text in required)


def test_ai_pending_and_missing_chinese_are_explicit():
    assert bilingual_status("AI_PENDING") == "AI待分析 · AI Pending"
    assert CHINESE_UNAVAILABLE == "暂未生成中文摘要"
    assert chinese_title("Unknown dynamic title") == "暂无中文标题"


def test_no_generic_chinese_ai_template_and_pending_is_single():
    assert "现有记录包含一个明确用户需求" not in APP_SOURCE
    assert APP_SOURCE.count("中文 AI 分析待补充 · Chinese AI analysis pending") == 1
    assert APP_SOURCE.count("中文产品梗概待补充 · Chinese product summary pending") <= 2


def test_body_uses_grouped_language_blocks():
    assert "**ENGLISH**" in APP_SOURCE
    assert "**中文**" in APP_SOURCE
    assert "render_ai_english(product)" in APP_SOURCE
    assert "render_ai_chinese(product)" in APP_SOURCE


def test_web_app_does_not_import_ai_provider_or_scrapers():
    assert "ai_providers" not in APP_SOURCE
    assert "scrapers" not in APP_SOURCE
    assert "GeminiProvider" not in APP_SOURCE
