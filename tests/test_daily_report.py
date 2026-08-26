"""Tests for the local Phase 9.4 Daily Report foundation."""

from daily_ranker import select_daily_top, select_full_qualified
from daily_report import build_daily_report, render_daily_report_html, write_daily_report_html
from daily_audit import SourceFunnelRow, SoftwareFunnelRow, write_source_audit, write_software_audit
from tests.test_daily_ranker import _op
from tests.test_deep_analysis import _result as deep_result


def test_missing_and_timeout_analysis_fall_back_to_triage():
    missing = _op(1, physical_analysis=None)
    ranking = select_daily_top([missing])
    report = build_daily_report(ranking, failed_candidate_ids={missing.candidate_id})
    item = report.items[0]
    assert item.research_status == "DEEP_ANALYSIS_FAILED"
    assert item.why_it_matters == missing.triage.primary_reason
    assert item.key_opportunity == missing.triage.key_opportunity
    assert item.recommended_next_step == "DEEP_RESEARCH_OPTIONAL"


def test_valid_deep_analysis_is_preferred_in_report():
    candidate = _op(1, physical_analysis=deep_result(deep_score=7))
    ranking = select_daily_top([candidate])
    report = build_daily_report(ranking)
    item = report.items[0]
    assert item.research_status == "DEEP_ANALYZED"
    assert item.deep_score == 7
    assert item.why_it_matters == candidate.physical_analysis.opportunity_summary
    assert item.key_opportunity == candidate.physical_analysis.micro_innovation_ideas[0]


def test_report_respects_existing_ranking_caps_and_source_url():
    candidates = [_op(i, theme="bags_and_carry") for i in range(1, 13)]
    report = build_daily_report(select_daily_top(candidates))
    assert len(report.items) <= 10
    assert sum(item.theme == "bags_and_carry" for item in report.items) <= 3
    assert all(item.source_url for item in report.items)


def test_html_is_local_safe_and_contains_no_raw_data_or_api_key(tmp_path):
    secret = "secret-api-key-must-not-appear"
    candidate = _op(1, raw_data={"GEMINI_API_KEY": secret, "private": "raw-only"})
    report = build_daily_report(select_daily_top([candidate]), report_date="2026-08-26")
    html = render_daily_report_html(report)
    path = write_daily_report_html(report, tmp_path)
    assert path.exists() and path.read_text(encoding="utf-8") == html
    assert candidate.source_url in html
    assert secret not in html and "raw-only" not in html
    assert "<script" not in html.casefold()
    assert "cdn" not in html.casefold()


def test_full_feed_has_no_top_ten_or_theme_hard_limit():
    candidates = [_op(i, theme="bags_and_carry") for i in range(1, 13)]
    top = select_daily_top(candidates)
    qualified = select_full_qualified(candidates)
    report = build_daily_report(top, qualified=qualified)
    assert len(top.final) <= 10
    assert len(report.items) == 12
    assert len(report.top_picks) <= 3


def test_third_qualified_software_remains_in_software_section():
    candidates = [_op(i, "Software", theme="software") for i in range(1, 5)]
    top = select_daily_top(candidates)
    qualified = select_full_qualified(candidates)
    report = build_daily_report(top, qualified=qualified)
    html = render_daily_report_html(report)
    assert len(top.final) <= 2
    assert len(report.items) == 4
    assert html.count("Software Opportunity") >= 4


def test_bilingual_labels_original_content_and_safe_research_status():
    candidate = _op(1, title="Fanny pack without zipper")
    report = build_daily_report(
        select_daily_top([candidate]),
        qualified=select_full_qualified([candidate]),
        failed_candidate_ids={candidate.candidate_id},
    )
    html = render_daily_report_html(report)
    for label in ("为什么值得看", "Why It Matters", "机会方向", "Opportunity", "主要风险", "Main Risks", "下一步", "Next Step"):
        assert label in html
    assert "Fanny pack without zipper" in html
    assert "DEEP_ANALYSIS_FAILED" not in html
    assert 'target="_blank"' in html and 'rel="noopener noreferrer"' in html


def test_audit_documents_are_generated(tmp_path):
    source = [SourceFunnelRow("Reddit", 10, 3, 3, 2, 1, 1, 1, 1, "Stored evidence.")]
    software = [SoftwareFunnelRow("Tool", "product_hunt", "MISSING", None, "NOT_APPLICABLE", 35, "missing_triage", False)]
    source_path = write_source_audit(source, tmp_path / "source.md")
    software_path = write_software_audit(software, tmp_path / "software.md")
    assert "Daily Source Funnel Audit" in source_path.read_text(encoding="utf-8")
    assert "missing_triage" in software_path.read_text(encoding="utf-8")
