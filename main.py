"""Product Picker multi-source pipeline entry point."""

from collections.abc import Callable, Iterable
from pathlib import Path
import sys
import os
import socket
import time

import db
from ai_filter import REAL_API_TEST_LIMIT, gemini_dry_run, openai_dry_run, run_triage_batch, select_diverse_candidates, select_real_test_candidates
from ai_providers import AIProviderError, MockAIProvider, create_provider
import config
from candidate_pool import (
    build_consumer_trend_candidate,
    build_demand_candidate,
    build_inspiration_candidate,
    build_validated_product_candidate,
    deduplicate_candidates,
)
from creative_content_filter import filter_creative_content
from commodity_filter import CommodityResult, filter_commodity
from demand_opportunity_filter import filter_demand_opportunity
from demand_signal_filter import classify_record_role, filter_demand_signal
from feasibility_filter import filter_feasibility
from models import Product
from rule_filter import filter_product
from performance_timing import query_profile, timed_stage
from scrapers.arctic_shift import ArcticShiftScraper
from scrapers.amazon_trends import AmazonTrendScraper, filter_amazon_trend
from scrapers.base_scraper import BaseScraper, ScraperError
from scrapers.kickstarter import KickstarterScraper
from scrapers.indiegogo import IndiegogoScraper
from scrapers.product_hunt import ProductHuntScraper
from scrapers.yanko_design import YankoDesignScraper


SEPARATOR = "=" * 23
DIVIDER = "-" * 24
MAX_ITEMS_PER_SOURCE = {
    "product_hunt": 50,
    "kickstarter": 100,
    "reddit_arctic_shift": 180,
    "amazon": 30,
    "yanko_design": 50,
    "indiegogo": 100,
}
SOURCE_LABELS = {
    "product_hunt": "Product Hunt",
    "kickstarter": "Kickstarter / KSInsights",
    "reddit_arctic_shift": "Reddit / Arctic Shift",
    "amazon": "Amazon",
    "yanko_design": "Yanko Design",
    "indiegogo": "Indiegogo",
}
SCRAPERS: list[BaseScraper] = [
    ProductHuntScraper(),
    KickstarterScraper(),
    ArcticShiftScraper(),
    AmazonTrendScraper(),
    YankoDesignScraper(),
    IndiegogoScraper(),
]


def run_pipeline(
    scrapers: Iterable[BaseScraper] | None = None,
    output: Callable[[str], None] = print,
    *,
    run_id: str | None = None,
    finish_run: bool = True,
) -> bool:
    """Fetch all sources independently, filter products, and save them."""
    output(SEPARATOR)
    output("Product Picker Pipeline")
    output(SEPARATOR)

    with query_profile(output, "database_init"):
        if not db.init_db():
            output("Database initialization failed")
            return False
    run_id = run_id or db.start_pipeline_run()
    existing_urls = db.get_all_product_urls()
    existing_candidate_ids = {
        candidate.candidate_id for candidate in db.get_all_candidates()
    }
    source_stats: dict[str, dict] = {}
    products: list[Product] = []
    total_fetched = 0
    for scraper in scrapers if scrapers is not None else SCRAPERS:
        source_label = SOURCE_LABELS.get(
            scraper.source_name,
            scraper.source_name.replace("_", " ").title(),
        )
        output("\nSource:")
        output(source_label)
        try:
            with timed_stage(output, "fetch", source=scraper.source_name):
                source_products = scraper.fetch()
        except ScraperError as exc:
            output("Unavailable")
            output(f"Reason: {exc}")
            output("Fetched:\n0")
            output("Processed:\n0")
            source_stats[scraper.source_name] = {
                "fetched": 0, "products": [], "failed": True, "error": str(exc),
            }
            if run_id:
                db.record_pipeline_source_run(
                    run_id, scraper.source_name, failed=True, error=str(exc)
                )
            continue
        fetched_count = len(source_products)
        limit = MAX_ITEMS_PER_SOURCE.get(scraper.source_name, 50)
        processed_products = source_products[:limit]
        total_fetched += fetched_count
        products.extend(processed_products)
        source_stats[scraper.source_name] = {
            "fetched": fetched_count, "products": processed_products,
            "failed": False, "error": "",
        }
        output(f"Fetched:\n{len(source_products)}")
        output(f"Processed:\n{len(processed_products)}")

    results = []
    filter_results = {}
    role_results_list = []
    record_role_results = {}
    feasibility_pairs = []
    feasibility_results = {}
    demand_pairs = []
    demand_signal_results = {}
    opportunity_pairs = []
    demand_opportunity_results = {}
    commodity_results = {}
    creative_results = {}
    for source_name, stats in source_stats.items():
        if stats["failed"]:
            continue
        with timed_stage(output, "process", source=source_name):
            for product in stats["products"]:
                filter_result = filter_product(product)
                results.append(filter_result)
                filter_results[product.url] = filter_result
                role = classify_record_role(product, filter_result.opportunity_type)
                role_results_list.append(role)
                record_role_results[product.url] = role
                if role.record_role == "product":
                    feasibility = filter_feasibility(product)
                    feasibility_pairs.append((product, feasibility))
                    feasibility_results[product.url] = feasibility
                if role.record_role == "demand_signal":
                    demand = filter_demand_signal(product)
                    demand_pairs.append((product, demand))
                    demand_signal_results[product.url] = demand
                    if demand.signal_status in {"HIGH", "MEDIUM"}:
                        opportunity = filter_demand_opportunity(product, demand)
                        opportunity_pairs.append((product, opportunity))
                        demand_opportunity_results[product.url] = opportunity
                if product.source_platform == "amazon":
                    commodity_results[product.url] = filter_commodity(product)
                if product.source_platform == "yanko_design":
                    creative_results[product.url] = filter_creative_content(product)
    rejected_count = sum(result.status == "rejected" for result in results)
    uncertain_status_count = sum(result.status == "uncertain" for result in results)
    opportunity_type_counts = {
        opportunity_type: sum(
            result.opportunity_type == opportunity_type for result in results
        )
        for opportunity_type in (
            "physical", "software", "inspiration", "uncertain"
        )
    }
    physical_candidates = sum(
        result.opportunity_type == "physical" and result.status == "candidate"
        for result in results
    )
    software_candidates = sum(
        result.opportunity_type == "software" and result.status == "candidate"
        for result in results
    )
    funded_100_count = sum(
        product.source_platform == "kickstarter"
        and _percent_funded(product) is not None
        and _percent_funded(product) >= 100
        for product in products
    )
    feasibility_counts = {
        status: sum(
            result.feasibility_status == status
            for _product, result in feasibility_pairs
        )
        for status in ("PASS", "REVIEW", "REJECT")
    }
    feasible_physical_candidates = sum(
        rule_result.opportunity_type == "physical"
        and feasibility_result.feasibility_status == "PASS"
        for product, feasibility_result in feasibility_pairs
        for rule_result in (filter_results[product.url],)
    )
    rejection_risks = {
        risk: sum(
            result.feasibility_status == "REJECT" and risk in result.risk_flags
            for _product, result in feasibility_pairs
        )
        for risk in (
            "complex_electronics",
            "weapon_or_blade",
            "wireless",
            "high_regulation",
            "large_or_heavy",
            "high_engineering_barrier",
        )
    }
    role_counts = {
        role: sum(result.record_role == role for result in role_results_list)
        for role in ("product", "demand_signal", "software", "inspiration", "uncertain")
    }
    demand_status_counts = {
        status: sum(result.signal_status == status for _product, result in demand_pairs)
        for status in ("HIGH", "MEDIUM", "LOW")
    }
    demand_type_counts = {
        signal_type: sum(
            result.signal_type == signal_type for _product, result in demand_pairs
        )
        for signal_type in (
            "purchase_intent", "product_gap", "price_pain", "feature_request",
            "usage_problem", "recommendation_request", "DIY_workaround",
        )
    }
    demand_opportunity_counts = {
        status: sum(
            result.demand_opportunity_status == status
            for _product, result in opportunity_pairs
        )
        for status in ("PRODUCTIZABLE", "REVIEW", "NOT_FIT")
    }
    community_names = (
        "EDC", "ShutUpAndTakeMyMoney", "onebag", "BuyItForLife",
        "CampingGear", "organization",
    )
    productizable_by_subreddit = {
        community: sum(
            product.category.casefold() == community.casefold()
            and result.demand_opportunity_status == "PRODUCTIZABLE"
            for product, result in opportunity_pairs
        )
        for community in community_names
    }
    opportunity_flag_names = (
        "clear_feature_gap", "clear_usage_scenario", "clear_size_requirement",
        "clear_price_pain", "existing_simple_product", "low_tech_modification",
        "storage_or_organization", "portability_problem",
        "accessibility_problem", "appearance_positioning_gap", "DIY_workaround",
    )
    opportunity_flag_counts = {
        flag: sum(flag in result.opportunity_flags for _product, result in opportunity_pairs)
        for flag in opportunity_flag_names
    }
    saved_count = 0
    duplicate_count = 0
    for source_name, stats in source_stats.items():
        if stats["failed"]:
            continue
        source_products = stats["products"]
        with query_profile(output, "save", source=source_name):
            source_saved, source_duplicates = db.save_products(
                source_products,
                filter_results,
                feasibility_results,
                record_role_results,
                demand_signal_results,
                demand_opportunity_results,
                commodity_results,
                timing_output=output,
                initialize=False,
            )
        if source_products and source_saved == 0 and source_duplicates == 0:
            stats["failed"] = True
            stats["error"] = "Database persistence failed"
            output("Database persistence failed")
            if run_id:
                db.record_pipeline_source_run(
                    run_id, source_name, fetched=stats["fetched"],
                    failed=True, error=stats["error"],
                )
            continue
        saved_count += source_saved
        duplicate_count += source_duplicates
        # Phase 11 shadow path: record explicit run membership and build the
        # deterministic evidence projection without affecting legacy output,
        # candidate creation, AI qualification, UI, or notification behavior.
        if run_id:
            from evidence_shadow import process_products_for_run
            process_products_for_run(
                run_id, source_products, existing_urls=existing_urls,
            )
    with timed_stage(output, "candidate_creation_update"):
        validated_candidates = [
            candidate
            for product, feasibility_result in feasibility_pairs
            for candidate in (
                build_validated_product_candidate(
                    product,
                    feasibility_status=feasibility_result.feasibility_status,
                    feasibility_score=feasibility_result.feasibility_score,
                    positive_signals=feasibility_result.positive_signals,
                ),
            )
            if candidate is not None
        ]
        demand_candidates = [
            candidate
            for product, opportunity_result in opportunity_pairs
            for demand_result in (demand_signal_results[product.url],)
            for candidate in (
                build_demand_candidate(
                    product,
                    demand_opportunity_status=(
                        opportunity_result.demand_opportunity_status
                    ),
                    demand_opportunity_score=(
                        opportunity_result.demand_opportunity_score
                    ),
                    signal_score=demand_result.signal_score,
                    signal_type=demand_result.signal_type,
                    opportunity_flags=opportunity_result.opportunity_flags,
                ),
            )
            if candidate is not None
        ]
        inspiration_candidates = [
            candidate
            for product in products if product.source_platform == "yanko_design"
            for candidate in (build_inspiration_candidate(product, creative_results[product.url]),)
            if candidate is not None
        ]
        consumer_trend_candidates = [
            candidate
            for product in products if product.source_platform == "amazon"
            for trend_result in (filter_amazon_trend(product),)
            for commodity_result in (commodity_results[product.url],)
            for candidate in (
                build_consumer_trend_candidate(
                    product,
                    status=trend_result.status,
                    feasibility_score=trend_result.feasibility_score,
                    market_signal_score=trend_result.market_signal_score,
                    micro_innovation_score=trend_result.micro_innovation_score,
                    signals=trend_result.signals,
                    reason=trend_result.reason,
                    commodity_status=commodity_result.commodity_status,
                ),
            )
            if candidate is not None
        ]
        candidates = deduplicate_candidates(
            validated_candidates + demand_candidates
            + inspiration_candidates + consumer_trend_candidates
        )
        db.save_candidates(candidates)
    from opportunity_specificity import assess_specificity
    with timed_stage(output, "specificity_rule_filtering"):
        specificity_results = [
            (
                candidate.candidate_id,
                assess_specificity(
                    candidate.title, candidate.summary, candidate.signals,
                    candidate.candidate_type, candidate.source_platform,
                ),
            )
            for candidate in candidates
        ]
        db.save_specificity_results(specificity_results, rule_version="v1")

    with query_profile(output, "candidate_status_updates"):
        for source_name, stats in source_stats.items():
            if stats["failed"]:
                continue
            source_products = stats["products"]
            source_candidates = [
                c for c in candidates
                if c.source_platform == source_name
                and c.candidate_id not in existing_candidate_ids
            ]
            rejected = sum(
                filter_results[p.url].status == "rejected" for p in source_products
            )
            db.record_pipeline_source_run(
                run_id, source_name,
                fetched=stats["fetched"],
                new_count=sum(p.url not in existing_urls for p in source_products),
                updated_count=sum(p.url in existing_urls for p in source_products),
                rejected=rejected,
                candidates_created=len(source_candidates),
            )
    if run_id and finish_run:
        db.finish_pipeline_run(
            run_id,
            "PARTIAL" if any(s["failed"] for s in source_stats.values()) else "COMPLETED",
        )
    candidate_score_distribution = {
        "90-100": sum(90 <= item.candidate_score <= 100 for item in candidates),
        "80-89": sum(80 <= item.candidate_score <= 89 for item in candidates),
        "70-79": sum(70 <= item.candidate_score <= 79 for item in candidates),
        "<70": sum(item.candidate_score < 70 for item in candidates),
    }
    candidate_source_counts = {
        "Reddit EDC": sum(
            product.category.casefold() == "edc"
            for item in candidates
            for product in products
            if product.url == item.source_url
        ),
        "Reddit onebag": sum(
            product.category.casefold() == "onebag"
            for item in candidates
            for product in products
            if product.url == item.source_url
        ),
        "Reddit CampingGear": sum(
            product.category.casefold() == "campinggear"
            for item in candidates
            for product in products
            if product.url == item.source_url
        ),
        "Kickstarter": sum(
            item.candidate_type == "validated_product"
            and item.source_platform == "kickstarter"
            for item in candidates
        ),
    }

    output(f"\n{DIVIDER}")
    output(f"\nTotal fetched:\n{total_fetched}")
    output(f"\nTotal processed:\n{len(products)}")
    output("\nOpportunity Classification:")
    output(f"Physical:\n{opportunity_type_counts['physical']}")
    output(f"Software:\n{opportunity_type_counts['software']}")
    output(f"Inspiration:\n{opportunity_type_counts['inspiration']}")
    output(f"Uncertain:\n{opportunity_type_counts['uncertain']}")
    output("\nMarket Validation:")
    output(f"Kickstarter funded >=100%:\n{funded_100_count}")
    output("\nRule Filter:")
    output(f"Physical Candidates:\n{physical_candidates}")
    output(f"Software Candidates:\n{software_candidates}")
    output(f"Rejected:\n{rejected_count}")
    output(f"Uncertain:\n{uncertain_status_count}")
    output("\nRecord Roles:")
    output(f"Products:\n{role_counts['product']}")
    output(f"Demand Signals:\n{role_counts['demand_signal']}")
    output(f"Software:\n{role_counts['software']}")
    output(f"Inspiration:\n{role_counts['inspiration']}")
    output(f"Uncertain:\n{role_counts['uncertain']}")
    output("\nProduct Feasibility:")
    output(f"PASS:\n{feasibility_counts['PASS']}")
    output(f"REVIEW:\n{feasibility_counts['REVIEW']}")
    output(f"REJECT:\n{feasibility_counts['REJECT']}")
    output(
        f"\nFeasible Physical Candidates:\n{feasible_physical_candidates}"
    )
    output("\nTop rejection risks:")
    for risk, count in rejection_risks.items():
        output(f"{risk}:\n{count}")
    output("\nDemand Signals:")
    output(f"HIGH:\n{demand_status_counts['HIGH']}")
    output(f"MEDIUM:\n{demand_status_counts['MEDIUM']}")
    output(f"LOW:\n{demand_status_counts['LOW']}")
    output("\nDemand Types:")
    for signal_type, count in demand_type_counts.items():
        output(f"{signal_type}:\n{count}")
    output("\nDemand Opportunities:")
    for status, count in demand_opportunity_counts.items():
        output(f"{status}:\n{count}")
    output("\nProductizable by subreddit:")
    for community, count in productizable_by_subreddit.items():
        output(f"{community}:\n{count}")
    output("\nTop Opportunity Flags:")
    for flag, count in opportunity_flag_counts.items():
        output(f"{flag}:\n{count}")
    output("\nMicro-Innovation Candidate Pool:")
    output(f"Validated Product Candidates:\n{len(validated_candidates)}")
    output(f"Demand Opportunity Candidates:\n{len(demand_candidates)}")
    output(f"Total Candidates:\n{len(candidates)}")
    output("\nCandidate Score:")
    for score_range, count in candidate_score_distribution.items():
        output(f"{score_range}:\n{count}")
    output("\nTop Candidate Sources:")
    for source, count in candidate_source_counts.items():
        output(f"{source}:\n{count}")
    output(f"\nSaved:\n{saved_count}")
    output(f"Duplicates:\n{duplicate_count}")
    output(f"\nDatabase:\n{_display_database_path()}")
    output("\nCompleted.")
    return True


def _percent_funded(product: Product) -> float | None:
    value = product.raw_data.get("percent_funded")
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run_yanko_validation(
    scraper: BaseScraper | None = None,
    output: Callable[[str], None] = print,
) -> bool:
    """Run the isolated Yanko RSS-to-inspiration-candidate validation."""
    if not db.init_db():
        output("Yanko Design:\nDatabase initialization failed")
        return False

    yank_scraper = scraper or YankoDesignScraper()
    output("Yanko Design:")
    try:
        products = yank_scraper.fetch()[:50]
    except ScraperError as exc:
        output("Unavailable")
        output(f"Reason: {exc}")
        return False

    classified = [
        (product, filter_creative_content(product)) for product in products
    ]
    content_types = (
        "physical_product",
        "concept_product",
        "architecture",
        "vehicle",
        "technology_complex",
        "other",
    )
    type_counts = {
        content_type: sum(
            result.content_type == content_type for _product, result in classified
        )
        for content_type in content_types
    }
    new_count, duplicate_count = db.save_products(products)
    candidates = deduplicate_candidates(
        [
            candidate
            for product, result in classified
            for candidate in (build_inspiration_candidate(product, result),)
            if candidate is not None
        ]
    )
    db.save_candidates(candidates)

    all_candidates = db.get_all_candidates()
    candidate_counts = {
        candidate_type: sum(
            item.candidate_type == candidate_type for item in all_candidates
        )
        for candidate_type in (
            "validated_product", "demand_opportunity", "inspiration_product"
        )
    }
    themes = (
        "bags_and_carry",
        "storage_and_organization",
        "travel_accessories",
        "desk_and_office",
        "outdoor_accessories",
        "home_and_living",
        "pet_accessories",
        "apparel_accessories",
        "tools_and_edc",
        "other",
    )
    theme_counts = {
        theme: sum(_candidate_theme(item) == theme for item in all_candidates)
        for theme in themes
    }

    output(f"Fetched:\n{len(products)}")
    output(f"New:\n{new_count}")
    output(f"Duplicates:\n{duplicate_count}")
    output("\nContent Types:")
    for content_type in content_types:
        output(f"{content_type}:\n{type_counts[content_type]}")
    output(f"\nEligible Inspiration Products:\n{len(candidates)}")
    output(f"\nInspiration Candidates:\n{len(candidates)}")
    output("\nCandidate Pool:")
    output(f"Validated Product:\n{candidate_counts['validated_product']}")
    output(f"Demand Opportunity:\n{candidate_counts['demand_opportunity']}")
    output(f"Inspiration Product:\n{candidate_counts['inspiration_product']}")
    output(f"Total:\n{len(all_candidates)}")
    output("\nTheme Distribution:")
    for theme in themes:
        output(f"{theme}:\n{theme_counts[theme]}")
    output("\nBefore Yanko:")
    output("bags_and_carry = 13 / 31")
    output("\nAfter Yanko:")
    output(f"bags_and_carry = {theme_counts['bags_and_carry']} / {len(all_candidates)}")
    output("\nCheckpoint Top 15 Yanko Inspiration Candidates:")
    for rank, candidate in enumerate(
        sorted(candidates, key=lambda item: item.candidate_score, reverse=True)[:15],
        1,
    ):
        result = next(
            result
            for product, result in classified
            if product.url == candidate.source_url
        )
        summary = " ".join(candidate.summary.split())[:150]
        output(f"\nrank: {rank}")
        output(f"title: {candidate.title}")
        output(f"summary: {summary}")
        output(f"content_type: {result.content_type}")
        output(f"candidate_score: {candidate.candidate_score}")
        output(f"feasibility_score: {candidate.feasibility_score}")
        output(f"micro_innovation_score: {candidate.micro_innovation_score}")
        output(f"signals: {', '.join(candidate.signals)}")
        output(f"reason: {candidate.reason}")
        output(f"source_url: {candidate.source_url}")
    return True


def run_amazon_validation(
    scraper: BaseScraper | None = None,
    output: Callable[[str], None] = print,
) -> bool:
    """Run Amazon as an isolated, optional trend-source validation."""
    raw_output = output

    def safe_output(message: str) -> None:
        try:
            raw_output(message)
        except UnicodeEncodeError:
            raw_output(message.encode("gbk", errors="replace").decode("gbk"))

    output = safe_output
    if not db.init_db():
        output("Amazon:\nDatabase initialization failed")
        return False

    amazon_scraper = scraper or AmazonTrendScraper()
    output("Amazon Consumer Trend Validation:")
    try:
        products = amazon_scraper.fetch()[:30]
    except ScraperError as exc:
        output("Unavailable")
        output(f"Reason: {exc}")
        output("Pipeline continued without Amazon.")
        return True

    classified = [(product, filter_amazon_trend(product)) for product in products]
    commodity_results = {
        product.url: filter_commodity(product) for product, _result in classified
    }
    new_count, duplicate_count = db.save_products(
        products, commodity_results=commodity_results
    )
    candidates = deduplicate_candidates([
        candidate
        for product, result in classified
        for candidate in (
            build_consumer_trend_candidate(
                product,
                status=result.status,
                feasibility_score=result.feasibility_score,
                market_signal_score=result.market_signal_score,
                micro_innovation_score=result.micro_innovation_score,
                signals=result.signals,
                reason=result.reason,
                commodity_status=commodity_results[product.url].commodity_status,
            ),
        )
        if candidate is not None
    ])
    db.replace_candidates_by_type("consumer_trend", candidates)

    source_counts = {
        source: sum(product.raw_data.get("source_list") == source for product in products)
        for source in ("new_releases", "movers_and_shakers")
    }
    output(f"Requests:\n{getattr(amazon_scraper, 'request_count', 0)}")
    output(f"Successful pages:\n{getattr(amazon_scraper, 'successful_pages', 0)}")
    output(f"Failed pages:\n{getattr(amazon_scraper, 'failed_pages', 0)}")
    output(f"Fetched:\n{len(products)}")
    output(f"New Releases:\n{source_counts['new_releases']}")
    output(f"Movers & Shakers:\n{source_counts['movers_and_shakers']}")
    output(f"Simple Physical:\n{sum(result.status == 'candidate' for _, result in classified)}")
    output(f"Rejected:\n{sum(result.status == 'rejected' for _, result in classified)}")
    output(f"Uncertain:\n{sum(result.status == 'uncertain' for _, result in classified)}")
    output(f"Consumer Trend Candidates:\n{len(candidates)}")
    output(f"Saved:\n{new_count}")
    output(f"Duplicates:\n{duplicate_count}")
    output("\nTop 15 Consumer Trend Candidates:")
    for rank, candidate in enumerate(
        sorted(candidates, key=lambda item: item.candidate_score, reverse=True)[:15], 1
    ):
        product = next(item for item in products if item.url == candidate.source_url)
        result = next(item for item_product, item in classified if item_product.url == candidate.source_url)
        raw = product.raw_data
        output(f"\nrank: {rank}")
        output(f"title: {candidate.title}")
        output(f"source_list: {raw.get('source_list')}")
        output(f"category: {product.category}")
        output(f"theme: {result.theme}")
        output(f"candidate_score: {candidate.candidate_score}")
        output(f"feasibility_score: {candidate.feasibility_score}")
        output(f"market_signal_score: {candidate.market_validation_score}")
        output(f"micro_innovation_score: {candidate.micro_innovation_score}")
        output(f"rank_change: {raw.get('rank_change')}")
        output(f"price: {raw.get('price')}")
        output(f"rating: {raw.get('rating')}")
        output(f"review_count: {raw.get('review_count')}")
        output(f"signals: {', '.join(candidate.signals)}")
        output(f"reason: {candidate.reason}")
        output(f"source_url: {candidate.source_url}")
    return True


def run_amazon_commodity_reprocess(
    output: Callable[[str], None] = print,
) -> bool:
    """Reprocess stored Amazon trend candidates without network access."""
    raw_output = output

    def safe_output(message: str) -> None:
        try:
            raw_output(message)
        except UnicodeEncodeError:
            raw_output(message.encode("gbk", errors="replace").decode("gbk"))

    output = safe_output
    if not db.init_db():
        output("Amazon Consumer Trends:\nDatabase initialization failed")
        return False
    products = [
        product for product in db.get_all_products()
        if product.source_platform == "amazon"
        and filter_amazon_trend(product).status == "candidate"
    ]
    results: dict[str, CommodityResult] = {
        product.url: filter_commodity(product) for product in products
    }
    db.save_products(products, commodity_results=results)
    trend_results = {
        product.url: filter_amazon_trend(product) for product in products
    }
    candidates = [
        candidate
        for product in products
        for trend_result in (trend_results[product.url],)
        for candidate in (
            build_consumer_trend_candidate(
                product,
                status=trend_result.status,
                feasibility_score=trend_result.feasibility_score,
                market_signal_score=trend_result.market_signal_score,
                micro_innovation_score=trend_result.micro_innovation_score,
                signals=trend_result.signals,
                reason=trend_result.reason,
                commodity_status=results[product.url].commodity_status,
            ),
        )
        if candidate is not None
    ]
    db.replace_candidates_by_type(
        "consumer_trend", candidates,
    )
    counts = {
        status: sum(result.commodity_status == status for result in results.values())
        for status in ("PROMISING", "REVIEW", "COMMODITY")
    }
    output("Amazon Consumer Trends:")
    for status in ("PROMISING", "REVIEW", "COMMODITY"):
        output(f"{status}:\n{counts[status]}")
    output("\nCheckpoint 7:")
    for product in products:
        trend_result = trend_results[product.url]
        result = results[product.url]
        candidate_score = round(
            0.40 * trend_result.feasibility_score
            + 0.35 * trend_result.market_signal_score
            + 0.25 * trend_result.micro_innovation_score
        )
        output(f"\ntitle: {product.title}")
        output(f"candidate_score: {candidate_score}")
        output(f"commodity_status: {result.commodity_status}")
        output(f"commodity_score: {result.commodity_score}")
        output(f"commodity_flags: {', '.join(result.commodity_flags)}")
        output(f"commodity_reason: {result.commodity_reason}")
        output(f"feasibility_score: {trend_result.feasibility_score}")
        output(f"market_signal_score: {trend_result.market_signal_score}")
        output(f"micro_innovation_score: {trend_result.micro_innovation_score}")
    return True


def _candidate_theme(candidate: object) -> str:
    """Assign one simple audit-only theme without changing candidate data."""
    title = str(getattr(candidate, "title", "")).casefold()
    summary = str(getattr(candidate, "summary", "")).casefold()
    text = f"{title} {summary}"
    if any(term in title for term in ("backpacking pillow", "sleeping bag")):
        return "outdoor_accessories"
    if any(
        term in title
        for term in (
            "smart fabric", "merino", "wallet/card sleeve",
            "edc - wallet recommendations",
        )
    ):
        return "apparel_accessories"
    if any(
        term in title
        for term in (
            "packing and bag advice", "perfect waterbottle", "remaining gear advice",
        )
    ):
        return "travel_accessories"
    if any(
        term in title
        for term in (
            "considering adding an edc item", "pocket clip", "tried and true",
            "possible upgrades",
        )
    ):
        return "tools_and_edc"
    if any(
        term in title
        for term in (
            "backpack", "fanny", "cross body", "crossbody", "sling", "duffle",
            "carry bag", "companion bag", "one bag", "bagging", "purse", "pack",
            "patagonia 30 mlc",
        )
    ):
        return "bags_and_carry"
    if any(term in text for term in ("organizer", "organiser", "storage", "pouch")):
        return "storage_and_organization"
    if any(term in text for term in ("travel", "trip", "airplane", "airline", "packing")):
        return "travel_accessories"
    if any(term in text for term in ("desk", "journal", "office")):
        return "desk_and_office"
    if any(term in text for term in ("camping", "outdoor")):
        return "outdoor_accessories"
    if any(term in text for term in ("pet", "dog", "cat")):
        return "pet_accessories"
    if any(term in text for term in ("merino", "fabric", "apparel", "wallet", "card sleeve")):
        return "apparel_accessories"
    if any(term in text for term in ("edc", "tool", "clip", "key")):
        return "tools_and_edc"
    if any(term in text for term in ("home", "lamp", "kitchen", "living")):
        return "home_and_living"
    return "other"


def _display_database_path() -> str:
    try:
        return str(db.DB_PATH.relative_to(Path(__file__).resolve().parent))
    except ValueError:
        return str(db.DB_PATH)


def run_ai_triage_validation(output: Callable[[str], None] = print) -> bool:
    """Run the isolated offline mock triage against the current candidate pool."""
    if not db.init_db():
        output("AI Triage:\nDatabase initialization failed")
        return False
    candidates = db.get_all_candidates()
    products = {product.url: product for product in db.get_all_products()}
    batch = run_triage_batch(
        candidates, products=products, commodity=db.get_candidate_commodity(),
        provider=MockAIProvider(), has_result=db.has_triage_result,
        save_result=db.save_triage_result,
    )
    counts = {status: sum(item.triage_status == status for item in batch.processed) for status in ("PASS", "REVIEW", "REJECT")}
    output("AI Triage:")
    output(f"Eligible Candidates:\n{batch.eligible}")
    output(f"Selected:\n{batch.selected}")
    output(f"Skipped Existing:\n{batch.skipped_existing}")
    output(f"Processed:\n{len(batch.processed)}")
    for status in ("PASS", "REVIEW", "REJECT"):
        output(f"{status}:\n{counts[status]}")
    output(f"Errors:\n{batch.errors}")
    average = round(sum(batch.input_characters) / len(batch.input_characters), 1) if batch.input_characters else 0
    output(f"Average Input Characters:\n{average}")
    output(f"Max Input Characters:\n{max(batch.input_characters, default=0)}")
    by_id = {item.candidate_id: item for item in candidates}
    output("\nCheckpoint Top PASS:")
    for result in sorted((item for item in batch.processed if item.triage_status == "PASS"), key=lambda item: item.triage_score, reverse=True)[:10]:
        candidate = by_id[result.candidate_id]
        output(f"\ntitle: {candidate.title}")
        output(f"candidate_type: {candidate.candidate_type}")
        output(f"source_platform: {candidate.source_platform}")
        output(f"candidate_score: {candidate.candidate_score}")
        output(f"triage_score: {result.triage_score}")
        output(f"triage_status: {result.triage_status}")
        output(f"confidence: {result.confidence}")
        output(f"opportunity_type: {result.opportunity_type}")
        output(f"primary_reason: {result.primary_reason}")
        output(f"key_opportunity: {result.key_opportunity}")
        output(f"main_risks: {', '.join(result.main_risks)}")
    return True


def run_openai_dry_run_validation(output: Callable[[str], None] = print) -> bool:
    """Validate final OpenAI requests without creating a network request."""
    candidates = db.get_all_candidates()
    products = {product.url: product for product in db.get_all_products()}
    result = openai_dry_run(
        candidates, products=products, commodity=db.get_candidate_commodity(),
        model=config.OPENAI_TRIAGE_MODEL,
    )
    types = [item.candidate_type for item in result["selected"]]
    lengths = result["input_characters"]
    output("OpenAI Dry Run:")
    output(f"Configured:\n{'yes' if config.is_openai_configured() else 'no'}")
    output(f"Model:\n{result['model']}")
    output(f"Selected Candidates:\n{len(result['selected'])}")
    output(f"Candidate Types:\n{', '.join(types)}")
    output(f"Average Input Characters:\n{round(sum(lengths) / len(lengths), 1) if lengths else 0}")
    output(f"Max Input Characters:\n{max(lengths, default=0)}")
    output(f"Request Ready:\n{'yes' if result['request_ready'] else 'no'}")
    output("Network Request Sent:\nNO")
    return bool(result["request_ready"])


def run_openai_real_validation(output: Callable[[str], None] = print) -> bool:
    """Explicit future entry point, capped at five candidates."""
    if not config.is_openai_configured():
        output("OpenAI API key not configured")
        return False
    candidates = db.get_all_candidates()
    commodity = db.get_candidate_commodity()
    eligible = [c for c in candidates if c.candidate_type != "consumer_trend" or commodity.get(c.candidate_id, ("", 0))[0] == "PROMISING"]
    selected = select_real_test_candidates(eligible)
    try:
        provider = create_provider("openai", api_key=config.OPENAI_API_KEY, model=config.OPENAI_TRIAGE_MODEL)
    except AIProviderError as exc:
        output(str(exc))
        return False
    products = {product.url: product for product in db.get_all_products()}
    batch = run_triage_batch(selected, products=products, commodity=commodity, provider=provider, has_result=db.has_triage_result, save_result=db.save_triage_result)
    output(f"OpenAI Real Validation Processed:\n{len(batch.processed)}")
    output(f"Errors:\n{batch.errors}")
    return batch.errors == 0


def run_gemini_dry_run_validation(output: Callable[[str], None] = print) -> bool:
    """Validate final Gemini requests without creating a network request."""
    candidates = db.get_all_candidates()
    products = {product.url: product for product in db.get_all_products()}
    result = gemini_dry_run(candidates, products=products, commodity=db.get_candidate_commodity(), model=config.GEMINI_TRIAGE_MODEL)
    types = [item.candidate_type for item in result["selected"]]
    lengths = result["input_characters"]
    output("Gemini Dry Run:")
    output(f"Configured:\n{'yes' if config.is_gemini_configured() else 'no'}")
    output(f"Model:\n{result['model']}")
    output(f"Selected Candidates:\n{len(result['selected'])}")
    output(f"Candidate Types:\n{', '.join(types)}")
    output(f"Average Input Characters:\n{round(sum(lengths) / len(lengths), 1) if lengths else 0}")
    output(f"Max Input Characters:\n{max(lengths, default=0)}")
    output(f"Request Ready:\n{'yes' if result['request_ready'] else 'no'}")
    output("Network Request Sent:\nNO")
    return bool(result["request_ready"])


def run_gemini_real_validation(output: Callable[[str], None] = print) -> bool:
    """Explicit future Gemini entry point, capped at five candidates."""
    if not config.is_gemini_configured():
        output("Gemini API key not configured")
        return False
    candidates = db.get_all_candidates()
    commodity = db.get_candidate_commodity()
    eligible = [c for c in candidates if c.candidate_type != "consumer_trend" or commodity.get(c.candidate_id, ("", 0))[0] == "PROMISING"]
    selected = select_real_test_candidates(eligible)
    try:
        provider = create_provider("gemini", api_key=config.GEMINI_API_KEY, model=config.GEMINI_TRIAGE_MODEL)
    except AIProviderError as exc:
        output(str(exc))
        return False
    products = {product.url: product for product in db.get_all_products()}
    batch = run_triage_batch(selected, products=products, commodity=commodity, provider=provider, has_result=db.has_triage_result, save_result=db.save_triage_result)
    output("Gemini Real Triage Validation:")
    output(f"Model:\n{config.GEMINI_TRIAGE_MODEL}")
    output(f"Selected:\n{len(selected)}")
    output(f"API Calls Sent:\n{provider.api_calls_sent}")
    output(f"Successful:\n{len(batch.processed)}")
    output(f"Failed:\n{batch.errors}")
    usage = provider.usage if provider.usage_available else None
    output(f"Input Tokens:\n{usage['input_tokens'] if usage else 'unavailable'}")
    output(f"Output Tokens:\n{usage['output_tokens'] if usage else 'unavailable'}")
    output(f"Total Tokens:\n{usage['total_tokens'] if usage else 'unavailable'}")
    by_id = {candidate.candidate_id: candidate for candidate in selected}
    output("\nResults:")
    for index, result in enumerate(batch.processed, 1):
        candidate = by_id[result.candidate_id]
        mock = db.get_triage_result(candidate.candidate_id, "mock", "mock")
        output(f"\n{index}.")
        output(f"title: {candidate.title}")
        output(f"candidate_type: {candidate.candidate_type}")
        output(f"source_platform: {candidate.source_platform}")
        output(f"candidate_score: {candidate.candidate_score}")
        output(f"Mock: {mock.triage_status + ' / ' + str(mock.triage_score) if mock else 'unavailable'}")
        output(f"Gemini: {result.triage_status} / {result.triage_score}")
        output(f"confidence: {result.confidence}")
        output(f"opportunity_type: {result.opportunity_type}")
        output(f"primary_reason: {result.primary_reason}")
        output(f"key_opportunity: {result.key_opportunity}")
        output(f"main_risks: {', '.join(result.main_risks)}")
        output(f"needs_deep_analysis: {result.needs_deep_analysis}")
    return batch.errors == 0


def run_gemini_connectivity_validation(
    output: Callable[[str], None] = print,
    provider=None,
) -> bool:
    """Send one minimal check, then at most one real candidate if successful."""
    if provider is None:
        if not config.is_gemini_configured():
            output("Gemini API key not configured")
            return False
        try:
            provider = create_provider(
                "gemini", api_key=config.GEMINI_API_KEY,
                model=config.GEMINI_TRIAGE_MODEL,
            )
        except AIProviderError as exc:
            output(str(exc))
            return False
    connectivity_schema = {
        "type": "object", "additionalProperties": False,
        "required": ["ok"],
        "properties": {"ok": {"type": "boolean"}},
    }
    started = time.monotonic()
    error = None
    try:
        provider.analyze(
            {"check": "connectivity"},
            "Return {\"ok\": true}. This is a connectivity check only.",
            connectivity_schema,
            allow_retry=False,
        )
        success = True
    except AIProviderError as exc:
        success = False
        error = exc
    elapsed = round(time.monotonic() - started, 2)
    error_text = str(error) if error else "none"
    auth = "invalid" if any(term in error_text.casefold() for term in ("401", "403", "authentication", "permission")) else ("valid" if success else "unknown")
    output("Gemini Connectivity:")
    output("Request Sent:\nyes")
    output(f"Success:\n{'yes' if success else 'no'}")
    output(f"Elapsed Seconds:\n{elapsed}")
    output(f"HTTP / SDK Error Type:\n{error_text}")
    output(f"Authentication:\n{auth}")
    output(f"Model Accessible:\n{'yes' if success else 'unknown'}")
    if not success:
        output("\nCandidate Test:\nExecuted:\nno")
        output("\nNetwork diagnostic:")
        try:
            socket.getaddrinfo("generativelanguage.googleapis.com", 443)
            dns = "resolved"
        except OSError as exc:
            dns = f"failed ({type(exc).__name__})"
        try:
            with socket.create_connection(("generativelanguage.googleapis.com", 443), timeout=5):
                https = "connected"
        except OSError as exc:
            https = f"failed ({type(exc).__name__})"
        output(f"DNS: {dns}")
        output(f"HTTPS 443: {https}")
        for name in ("HTTPS_PROXY", "HTTP_PROXY", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
            output(f"{name}: {'set' if os.getenv(name) else 'not set'}")
        return False

    usage_before = dict(provider.usage)
    candidates = db.get_all_candidates()
    commodity = db.get_candidate_commodity()
    eligible = [c for c in candidates if c.candidate_type != "consumer_trend" or commodity.get(c.candidate_id, ("", 0))[0] == "PROMISING"]
    candidate = select_real_test_candidates(eligible)[0]
    products = {product.url: product for product in db.get_all_products()}
    batch = run_triage_batch(
        [candidate], products=products, commodity=commodity, provider=provider,
        has_result=db.has_triage_result, save_result=db.save_triage_result,
    )
    output("\nCandidate Test:")
    output("Executed:\nyes")
    if batch.processed:
        result = batch.processed[0]
        usage = {key: provider.usage[key] - usage_before[key] for key in provider.usage}
        output(f"title: {candidate.title}")
        output(f"triage_status: {result.triage_status}")
        output(f"triage_score: {result.triage_score}")
        output(f"confidence: {result.confidence}")
        output(f"Input Tokens: {usage['input_tokens'] if provider.usage_available else 'unavailable'}")
        output(f"Output Tokens: {usage['output_tokens'] if provider.usage_available else 'unavailable'}")
        output(f"Total Tokens: {usage['total_tokens'] if provider.usage_available else 'unavailable'}")
        return True
    output(f"Error: candidate analysis failed ({batch.errors})")
    return False


def main() -> None:
    if "--ai-triage-openai-dry-run" in sys.argv:
        run_openai_dry_run_validation()
    elif "--ai-triage-openai-test" in sys.argv:
        run_openai_real_validation()
    elif "--ai-triage-gemini-dry-run" in sys.argv:
        run_gemini_dry_run_validation()
    elif "--ai-triage-gemini-test" in sys.argv:
        run_gemini_real_validation()
    elif "--ai-triage-gemini-connectivity" in sys.argv:
        run_gemini_connectivity_validation()
    else:
        run_pipeline()


if __name__ == "__main__":
    main()
