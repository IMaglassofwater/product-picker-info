"""Offline source and software funnel audits for the Daily Report."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import sqlite3

import db
from daily_ranker import HARD_RISKS, OpportunityInput, RankedOpportunity, apply_quality_gate, score_candidate
from opportunity_specificity import assess_specificity


SOURCE_ORDER = (
    ("Reddit", ("reddit",)),
    ("Amazon", ("amazon",)),
    ("Yanko Design", ("yanko",)),
    ("Product Hunt", ("product_hunt",)),
    ("Kickstarter", ("kickstarter", "ksinsights")),
    ("Indiegogo", ("indiegogo",)),
)


@dataclass(frozen=True)
class SourceFunnelRow:
    source: str
    fetched: int
    candidates: int
    passed_filters: int
    triage_eligible: int
    triage_pass: int
    specific: int
    qualified: int
    displayed: int
    main_reason: str
    triage_review: int = 0
    triage_reject: int = 0
    triage_missing: int = 0


@dataclass(frozen=True)
class SoftwareFunnelRow:
    title: str
    source: str
    triage_status: str
    triage_score: int | None
    specificity_status: str
    final_score: int
    exclusion_reason: str
    qualified: bool


def _matches(source: str, aliases: tuple[str, ...]) -> bool:
    value = source.casefold()
    return any(alias in value for alias in aliases)


def build_source_funnel(
    candidates: list[OpportunityInput], qualified: list[RankedOpportunity]
) -> list[SourceFunnelRow]:
    qualified_ids = {item.candidate.candidate_id for item in qualified}
    with sqlite3.connect(db.DB_PATH) as connection:
        fetched_by_source = Counter(dict(connection.execute(
            "SELECT source_platform, COUNT(*) FROM products GROUP BY source_platform"
        ).fetchall()))

    output = []
    for label, aliases in SOURCE_ORDER:
        source_candidates = [c for c in candidates if _matches(c.source_platform, aliases)]
        passed_filters = sum(
            bool(c.title.strip() and c.source_url.strip())
            and not {value.casefold() for value in c.risk_flags + c.signals}.intersection(HARD_RISKS)
            for c in source_candidates
        )
        fetched = sum(count for source, count in fetched_by_source.items() if _matches(source, aliases))
        triaged = [c for c in source_candidates if c.triage and c.triage.provider == "gemini"]
        passed = [c for c in triaged if c.triage.triage_status == "PASS"]
        specific = 0
        for candidate in passed:
            if candidate.opportunity_type == "Software":
                continue
            result = assess_specificity(
                candidate.title, candidate.summary, candidate.signals,
                candidate.candidate_type, candidate.source_platform,
            )
            specific += result.specificity_status == "SPECIFIC"
        qualified_count = sum(c.candidate_id in qualified_ids for c in source_candidates)
        statuses = Counter(c.triage.triage_status if c.triage else "MISSING" for c in source_candidates)
        if fetched == 0:
            reason = "No records exist in the current database."
        elif not source_candidates:
            reason = "Fetched records produced no current normalized ranking candidates."
        elif not triaged:
            reason = "Current candidates have no stored Gemini triage result."
        elif not passed:
            reason = f"No Triage PASS records (MISSING {statuses['MISSING']}, REVIEW {statuses['REVIEW']}, REJECT {statuses['REJECT']})."
        elif qualified_count == 0:
            reason = "Triage-passed records did not pass the current hard-risk/specificity gates."
        else:
            reason = "Qualified records passed stored Gemini triage and current offline gates."
        output.append(SourceFunnelRow(
            label, fetched, len(source_candidates), passed_filters, len(triaged), len(passed),
            specific, qualified_count, qualified_count, reason,
            statuses["REVIEW"], statuses["REJECT"], statuses["MISSING"],
        ))
    return output


def build_software_funnel(
    candidates: list[OpportunityInput], qualified: list[RankedOpportunity]
) -> list[SoftwareFunnelRow]:
    qualified_ids = {item.candidate.candidate_id for item in qualified}
    rows = []
    for candidate in candidates:
        if candidate.opportunity_type != "Software":
            continue
        passed, reason = apply_quality_gate(candidate)
        is_qualified = candidate.candidate_id in qualified_ids
        if passed and not is_qualified:
            reason = "report_readiness"
        rows.append(SoftwareFunnelRow(
            title=candidate.title,
            source=candidate.source_platform,
            triage_status=candidate.triage.triage_status if candidate.triage else "MISSING",
            triage_score=candidate.triage.triage_score if candidate.triage else None,
            specificity_status="NOT_APPLICABLE",
            final_score=score_candidate(candidate).final_rank_score,
            exclusion_reason="" if is_qualified else reason,
            qualified=is_qualified,
        ))
    return sorted(rows, key=lambda row: (-row.final_score, row.title.casefold()))


def write_source_audit(rows: list[SourceFunnelRow], path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Daily Source Funnel Audit", "",
        "| Source | Products | Candidates | Gemini PASS | Gemini REVIEW | Gemini REJECT | MISSING | Qualified | Displayed | Main reason |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    lines.extend(
        f"| {r.source} | {r.fetched} | {r.candidates} | {r.triage_pass} | {r.triage_review} | {r.triage_reject} | {r.triage_missing} | {r.qualified} | {r.displayed} | {r.main_reason} |"
        for r in rows
    )
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def write_software_audit(rows: list[SoftwareFunnelRow], path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter(row.triage_status for row in rows)
    with sqlite3.connect(db.DB_PATH) as connection:
        total_products = connection.execute(
            "SELECT COUNT(*) FROM products WHERE record_role = 'software' OR opportunity_type = 'software'"
        ).fetchone()[0]
    product_hunt = sum("product_hunt" in row.source.casefold() for row in rows)
    lines = [
        "# Software Funnel Audit", "",
        f"Total Software Products: {total_products}",
        f"Software Candidates: {len(rows)}", f"PASS: {counts['PASS']}",
        f"REVIEW: {counts['REVIEW']}", f"REJECT: {counts['REJECT']}",
        f"MISSING: {counts['MISSING']}",
        f"Qualified: {sum(row.qualified for row in rows)}",
        f"Displayed: {sum(row.qualified for row in rows)}",
        f"Product Hunt Contribution: {product_hunt}",
        f"Other Source Contribution: {len(rows) - product_hunt}", "",
        "| Title | Source | Triage | Triage Score | Specificity | Final Score | Qualified | Exclusion Reason |",
        "|---|---|---|---:|---|---:|---|---|",
    ]
    for row in rows:
        title = row.title.replace("|", "\\|")
        lines.append(
            f"| {title} | {row.source} | {row.triage_status} | {row.triage_score if row.triage_score is not None else ''} | {row.specificity_status} | {row.final_score} | {'yes' if row.qualified else 'no'} | {row.exclusion_reason} |"
        )
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
