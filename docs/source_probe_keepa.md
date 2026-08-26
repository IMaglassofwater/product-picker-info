# Keepa Cost & Capability Probe

Probe date: 2026-08-25

This report uses only current Keepa official documentation and the official Keepa subscription page. No Keepa API request, registration, purchase, library installation, database access, test run, scraper execution, or business-code change was made.

## Executive Summary

Keepa has the structured product, category, price, sales-rank, history, statistics, Best Sellers, Product Finder and Deals capabilities needed for an Amazon market-intelligence layer. Its Product statistics expose current sales rank and fixed 30/90/180-day averages, and Product objects expose sales-rank history, so a future rule can detect a current rank that is materially better than its historical average.

Keepa does not document a direct Amazon Movers & Shakers or New Releases endpoint. Rising products are derivable from rank and change data. Recently launched products are derivable, imperfectly, through Product Finder fields such as `listedSince`, `releaseDate`, `publicationDate`, and `trackingSince`.

The official public pricing page did not render plan names, monthly prices, or current plan refill rates during this probe. Official documentation confirms that an API subscription is required, plans are prepaid monthly with automatic renewal, and cancellation is allowed at any time. Consequently, current monetary price and lowest-plan capacity are `UNKNOWN`, and the purchase recommendation is `NOT YET`.

## Capabilities

| Capability | Status | Official endpoint / mechanism | Product Picker value |
| --- | --- | --- | --- |
| Product Data | AVAILABLE | `GET /product` | USEFUL |
| Sales Rank / BSR | AVAILABLE | Product `csv`; Statistics `current[SALES]`; Product Finder `current_SALES` | ESSENTIAL |
| Sales Rank History | AVAILABLE | Product `salesRanks` and `csv`; history is included unless `history=0` | ESSENTIAL |
| Price History | AVAILABLE | Product `csv`; optional `days`; Statistics current/averages | USEFUL |
| Best Sellers | AVAILABLE | `GET /bestsellers` | USEFUL |
| Deals | AVAILABLE | `GET/POST /deal`; Lightning Deals separately at `/lightningdeal` | USEFUL |
| Product Search | AVAILABLE | `GET /search?type=product` | UNNECESSARY for routine trend discovery |
| Product Finder | AVAILABLE | `GET/POST /query` | ESSENTIAL |
| Category / Browse Node | AVAILABLE | `/category`; `/search?type=category`; category filters | ESSENTIAL |
| Review / Rating data | PARTIAL | Product request with `rating=1`; Product `reviews`/`csv` | USEFUL |
| New/recent product capability | PARTIAL | Product Finder `listedSince`, `releaseDate`, `publicationDate`, `trackingSince` | USEFUL |
| Movers / rank-growth capability | PARTIAL | Derive through `current_SALES`, `avg30/90/180_SALES`, deltas and rank history; Deals can include rank changes | ESSENTIAL |

Official documentation notes that rating/review information may be unavailable or outdated; variation-specific rating-count history has not been updated since April 9, 2025 because Amazon removed that data point. Product Finder searches Keepa's database, not Amazon directly, and may not contain every matching Amazon product.

## Token System

### Access-key creation and refill model

- Subscribe to an API plan on `https://keepa.com/#!api`.
- The API access key becomes available on the Keepa API account page and can be viewed or regenerated there.
- Every API call requires the private key.
- A plan continuously generates a fixed number of tokens per minute, 24/7.
- Tokens expire after 60 minutes; bucket capacity is `refill rate × 60`.
- Plans are prepaid for one month and renew automatically.
- Keepa states that a subscription can be canceled at any time.

The token system is a rolling one-hour bucket, not a monthly block of tokens that can be saved indefinitely. A daily job must fit the current bucket or wait for refill.

### Official endpoint costs

| Request | Official token cost |
| --- | --- |
| Product | 1 per requested ASIN; batch limit 100 ASINs, cost remains per ASIN |
| Product `stats` | No extra token |
| Product history | No extra token; history is included by default and `history=0` removes it |
| Product `rating=1` | Up to +1 per product when qualifying recent rating/review data exists |
| Product `update=0` | Up to +1 per product when Keepa updated it less than one hour ago |
| Product `offers` | Replaces base cost; 6 per found offer page of up to 10 offers; successful retrieval with no offer page costs 5 |
| Product `buybox=1` | +2 per product |
| Product `stock=1` with offers | Up to +2 per product under the documented freshness condition |
| Product Finder | 10 per request + 1 per 100 ASINs in the result set, rounded up |
| Product Finder `stats=1` | Additionally 30 + 1 per 1,000,000 total matched products |
| Product Search | 10 per result page, up to 10 results |
| Best Sellers | 50 per requested category list, up to 100,000 ASINs |
| Browsing Deals | 5 per request, up to 150 deals |
| Category Lookup | 1 per request; up to 10 category IDs and optional parent tree add no cost |
| Category Search | 1 per search |
| Lightning Deal by ASIN | 1 per deal |
| Full Lightning Deals list | 500 |

Optional Offers, Buy Box and Stock data are not required for Product Picker's first trend-discovery design and should be omitted.

## Current Official Pricing

| Item | Result |
| --- | --- |
| Lowest API plan name | UNKNOWN |
| Monthly price | UNKNOWN |
| Tokens per minute on lowest plan | UNKNOWN |
| Billing | Prepaid one month, automatic renewal |
| Cancel anytime | YES |
| Free API allowance | NO confirmed free API access; official docs require an API subscription and key |
| Trial | UNKNOWN |
| Free account API access | NO according to the documented subscription requirement |

The official public subscription shell loaded, but it did not expose plan cards or current prices in a publicly readable response. No third-party or historical price was substituted.

## Product Picker Required Data

| Required field | Keepa support | Mechanism / limitation |
| --- | --- | --- |
| ASIN | YES | Product object and discovery endpoint results |
| title | YES | Product and Deal objects |
| category | YES | `rootCategory`, `categories`, `categoryTree`; category endpoints |
| brand | YES | Product object; may be absent for incomplete listings |
| current price | PARTIAL | Product `csv`/Statistics `current`; depends on available price type/offer |
| rating | PARTIAL | `rating=1`; can be absent or stale |
| review_count | PARTIAL | `rating=1`; availability and freshness limitations apply |
| sales_rank | PARTIAL | Current `SALES` statistic when Keepa has rank data |
| sales_rank_history | PARTIAL | `salesRanks`/`csv`; history length and coverage vary |
| 30_day_average_rank | PARTIAL | Statistics `avg30[SALES]`; insufficient history can yield no value |
| 90_day_average_rank | PARTIAL | Statistics `avg90[SALES]`; insufficient history can yield no value |
| 180_day_average_rank | PARTIAL | Statistics `avg180[SALES]`; insufficient history can yield no value |
| product_creation_date | PARTIAL | `listedSince` is Keepa's best-known Amazon listing time and may be 0/-1; `releaseDate`/`publicationDate` may exist |
| image | YES | Product `images`; Deal image data |
| Amazon URL | YES, derived | Construct from marketplace domain and ASIN; no page scrape required |

## Ultra Cheap Architecture

Daily, one run:

1. One category-filtered Browsing Deals request across a small set of consumer categories: 5 tokens, up to 150 structured deal records.
2. Apply local free rules to Deal title, category, dimensions/attributes where available, and exclude complex or regulated products.
3. Request basic Product data with `stats` and history only for 5–10 survivors: 5–10 tokens.
4. Optionally request `rating=1` for those survivors: up to 5–10 additional tokens.

- Estimated daily tokens: 10–25
- Estimated 30-day tokens: 300–750
- Characteristics: lowest consumption; centered on recent price/rank changes rather than complete category coverage.

## Balanced Architecture

Target categories: Home, Office, Pet, Sports/Outdoors, Tools, and Travel/Luggage. Daily, one run:

1. One Browsing Deals query using included category nodes: 5 tokens; retain at most 100 locally.
2. One cross-category Product Finder query for approximately 50 recent/rank-filtered ASINs: 10 + 1 = 11 tokens.
3. Product requests for those 50 Product Finder ASINs so free physical/feasibility rules have titles, dimensions, attributes, current rank and history: 50 tokens. Use `stats=180`; do not request offers.
4. Merge and deduplicate the two discovery routes, process only 50–150 raw items, then keep about 10–30 candidates.
5. Request basic Product history/statistics for Deal-derived finalists not already resolved: 10–30 tokens.
6. Request `rating=1` only for the final 10–30 candidates when rating/review evidence is needed: up to 10–30 tokens.

- Estimated daily tokens: 86–126
- Estimated 30-day tokens: 2,580–3,780
- Required one-hour refill rate to finish without waiting: approximately 2–3 tokens/minute (`ceil(86/60)` to `ceil(126/60)`).

This design does not query Product details for every Deal record. Product Finder returns ASINs only, so its selected 50 require Product resolution; Deal records already contain enough structured information for preliminary free-rule filtering.

## High Coverage Architecture

Future reference only:

1. Six category-specific Product Finder requests, 100 ASINs per category: `6 × 11 = 66` tokens.
2. Basic Product history/statistics for 600 raw ASINs: 600 tokens.
3. Optional `rating=1` for 50–100 finalists: up to 50–100 tokens, plus a basic request if not already fetched.
4. Optional weekly Best Sellers lists for six categories: `6 × 50 = 300` tokens per weekly run.

- Daily core: 716–766 tokens
- 30-day core: 21,480–22,980 tokens
- Weekly Best Sellers overhead: 1,200–1,500 tokens per month depending on four or five weekly runs
- Total illustrative monthly range: 22,680–24,480 tokens
- Offers/Buy Box/Stock excluded.

## Balanced Token Calculation

### Minimum daily case

| Step | Calculation | Tokens |
| --- | ---: | ---: |
| Deals discovery | 1 request | 5 |
| Product Finder | 10 + `ceil(50/100)` | 11 |
| Resolve 50 Finder ASINs | 50 × 1 | 50 |
| Resolve 10 Deal-derived finalists | 10 × 1 | 10 |
| Rating/review for 10 finalists | up to 10 × 1 | 10 |
| Total | 5 + 11 + 50 + 10 + 10 | 86 |

### Maximum daily case

| Step | Calculation | Tokens |
| --- | ---: | ---: |
| Deals discovery | 1 request | 5 |
| Product Finder | 10 + `ceil(50/100)` | 11 |
| Resolve 50 Finder ASINs | 50 × 1 | 50 |
| Resolve 30 Deal-derived finalists | 30 × 1 | 30 |
| Rating/review for 30 finalists | up to 30 × 1 | 30 |
| Total | 5 + 11 + 50 + 30 + 30 | 126 |

Monthly at one run per day:

- Minimum: `86 × 30 = 2,580` tokens
- Maximum: `126 × 30 = 3,780` tokens

`stats` and price/sales-rank history add no Product-request token cost. The calculation intentionally excludes Offers, Buy Box, Stock and forced live updates.

### Is the lowest plan sufficient?

UNKNOWN. The workload needs a bucket of 126 tokens for the upper daily case, or a refill rate of at least 3 tokens/minute to finish within one hour without waiting. The official public pricing page did not expose the lowest plan's refill rate, so capacity cannot be asserted as a current pricing fact.

## Trend Detection Potential

Keepa supports a future “recently rising product” rule without relying only on current Best Sellers:

- Statistics `current[SALES]` supplies current sales rank.
- Statistics `avg30[SALES]`, `avg90[SALES]`, and `avg180[SALES]` supply fixed-window weighted averages.
- Product `salesRanks`/`csv` supply rank history.
- Statistics include `salesRankDrops30/90/180/365`.
- Product Finder supports current, average, delta and delta-percent fields by price type, including `SALES`.
- Deals represent products with recent price or sales-rank changes and expose day/week/month/90-day comparison windows.
- Price history can distinguish rank movement accompanied by price promotions.

The data supports a future rule such as “current rank is materially better (numerically lower) than the 90-day average,” subject to missing or insufficient history. No trend algorithm was implemented in this phase.

### Movers support

- Direct Movers & Shakers endpoint: NOT AVAILABLE in official documentation
- Equivalent rank-growth discovery: DERIVABLE / PARTIAL through Product Finder, Deals, Statistics and rank history

## New Releases Support

- Direct Amazon New Releases endpoint: NOT AVAILABLE in official documentation
- Product Picker status: DERIVABLE

Product Finder can filter and sort with `listedSince`, `releaseDate`, `publicationDate`, `trackingSince`, current sales rank, review presence, category, dimensions, weight, battery flags and product type. This can approximate “recently launched and beginning to receive feedback.” It is not identical to Amazon's New Releases list because `listedSince` is only Keepa's best-known first-listing time, can be unavailable, and Keepa's product database may be incomplete.

## Amazon HTML vs Keepa

| Dimension | Architecture A: Amazon HTML | Architecture B: Keepa API |
| --- | --- | --- |
| Data Stability | LOW | HIGH |
| Development Complexity | MEDIUM | MEDIUM |
| Maintenance Cost | HIGH | LOW |
| Historical Data | LOW | HIGH |
| Trend Detection | LOW–MEDIUM | HIGH |
| Structured Fields | LOW | HIGH |
| Anti-Bot Risk | HIGH | LOW |
| Monthly Monetary Cost | LOW | UNKNOWN, non-zero subscription required |

Keepa is technically better suited than a long-lived Amazon HTML scraper for historical trend analysis. Its monetary tradeoff cannot be finalized until the current official plan price and refill rate are visible.

## Recommendation

### Required cost conclusions

1. **Is the lowest API plan enough for one daily Product Picker run?** UNKNOWN. Balanced needs 86–126 tokens per run and at least a 126-token burst, or 3 tokens/minute to complete within one hour without waiting.
2. **Balanced token estimate:** 86–126 tokens/day; 2,580–3,780 tokens per 30-day month.
3. **Should every raw Amazon product use Product Request?** No. Deals provide structured discovery data. Apply free rules first and request Product history/details only for finalists. Product Finder returns only ASINs, so its selected subset must be resolved before content filtering.
4. **Is Keepa preferable to maintaining Amazon HTML scraping?** YES technically: structured history, stable fields, trend statistics and low anti-bot risk outweigh the lower maintenance burden; monetary price remains unresolved.
5. **Should the user pay for Keepa now?** NOT YET.

Before any purchase decision, verify the current lowest plan's official dashboard price, token refill rate, and whether a trial exists. Then confirm with a very small authorized sample that the target six categories have sufficient `listedSince`, sales-rank history, rating/review and physical-product coverage. No subscription is justified until those current commercial facts and sample-coverage gaps are resolved.

### Official sources

- Overview: https://keepa.com/api-docs/
- Plans and tokens: https://keepa.com/api-docs/plans-tokens.html
- Product Request: https://keepa.com/api-docs/product.html
- Product Object: https://keepa.com/api-docs/product-object.html
- Statistics Object: https://keepa.com/api-docs/statistics-object.html
- Product Finder: https://keepa.com/api-docs/product-finder.html
- Best Sellers: https://keepa.com/api-docs/best-sellers.html
- Browsing Deals: https://keepa.com/api-docs/deals.html
- Official API subscription page: https://keepa.com/#!api
