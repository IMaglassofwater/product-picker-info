# Amazon Consumer Trend Source Probe

Probe date: 2026-08-25

Scope: low-volume, read-only access testing of public Amazon.com ranking pages. No login, CAPTCHA bypass, proxy, paid service, AI call, database write, pipeline run, or formal scraper was used. No eBay, Etsy, TikTok Shop, or Walmart source was investigated.

## 1. Access Summary

### Movers & Shakers

- Public URL: https://www.amazon.com/gp/movers-and-shakers/home-garden
- Category: Home & Kitchen
- Direct HTTP result: 200 HTML
- Page title: “Amazon.com Movers & Shakers: The biggest gainers in Home & Kitchen sales rank over the past 24 hours”
- Product grid in the tested response: unavailable
- Valid products parsed: 0
- Access: PARTIAL

The public page itself was reachable and identified the list as 24-hour sales-rank gainers, but its response did not contain a usable product grid. No login, alternate identity, proxy, CAPTCHA bypass, pagination, or additional category request was attempted.

### New Releases

- Public URL: https://www.amazon.com/gp/new-releases/home-garden
- Category: Home & Kitchen
- Direct HTTP result: 200 HTML
- Page title: “Amazon.com New Releases: The best-selling new & future releases in Home & Kitchen”
- Product grid in the tested response: available
- Valid products parsed: 30
- Access: AVAILABLE

The first Home & Kitchen page supplied the full 30-record probe limit, so no other category or page was requested.

### Authentication

- Authentication Required: NO for the two tested public pages

## 2. Field Stability

The counts below refer to the 30 valid New Releases samples. Movers & Shakers yielded no valid product rows.

| Field | Availability | Sample coverage |
| --- | --- | ---: |
| rank | AVAILABLE | 30 / 30 |
| title | AVAILABLE | 30 / 30 |
| url | AVAILABLE | 30 / 30 |
| ASIN | AVAILABLE | 30 / 30 |
| price | PARTIAL | 24 / 30 |
| rating | PARTIAL | 29 / 30 |
| review_count | PARTIAL | 29 / 30 |
| category | AVAILABLE | 30 / 30, page-level Home & Kitchen |
| rank_change | UNAVAILABLE | 0 / 30 |
| growth_percentage | UNAVAILABLE | 0 / 30 |
| image_url | AVAILABLE | 30 / 30 |

No rank change or growth percentage was inferred from rank, rating, reviews, or any other field.

## 3. Probe-only Product Classification

Classification used fixed title rules only. Powered, battery, UV, electric, smart, dehumidifier and air-purifier items were marked `complex_electronics`; pest-control or aerosol chemical items were marked `regulated`; bed frames, gaming chairs and full-length floor mirrors were marked `large_or_heavy`. No existing scoring or feasibility pipeline was called.

| Product type | Count |
| --- | ---: |
| simple_physical | 13 |
| complex_electronics | 11 |
| regulated | 3 |
| large_or_heavy | 3 |
| software_or_digital | 0 |
| other | 0 |
| Total Samples | 30 |

- Simple Physical Rate: 43.3%

## 4. Simple Physical Theme Distribution

Each of the 13 `simple_physical` samples has one primary theme.

| Theme | Count |
| --- | ---: |
| bags_and_carry | 1 |
| storage_and_organization | 2 |
| travel_accessories | 3 |
| desk_and_office | 0 |
| outdoor_accessories | 3 |
| home_and_living | 2 |
| pet_accessories | 0 |
| apparel_accessories | 0 |
| tools_and_edc | 1 |
| cleaning | 1 |
| hobby_and_craft | 0 |
| other | 0 |
| Total | 13 |

The sample adds observable Home & Kitchen, travel, outdoor, storage, cleaning, and manual-tool directions. It did not provide pet, apparel, craft, or standalone office-product simple samples in this single category page.

## 5. Top Simple Physical Samples

All 13 qualifying samples are shown in New Releases rank order. Amazon displayed localized CNY prices in the tested response.

### 1. Pocket Hose Ballistic 100 FT Expandable Garden Hose

- source_list: New Releases
- rank: 1
- rank_change: unavailable
- category: Home & Kitchen
- theme: outdoor_accessories
- price: CNY 470.47
- rating: 4.3
- review_count: 3,313
- ASIN: B0GWFF75Z5
- url: https://www.amazon.com/dp/B0GWFF75Z5

### 2. STANLEY Quencher ProTour Flipstraw Tumbler, 30 oz

- source_list: New Releases
- rank: 2
- rank_change: unavailable
- category: Home & Kitchen
- theme: travel_accessories
- price: CNY 189.69
- rating: 4.7
- review_count: 19,928
- ASIN: B0H1YJM5W8
- url: https://www.amazon.com/dp/B0H1YJM5W8

### 3. MOSROAD Tea Lights Candles 80 Pack

- source_list: New Releases
- rank: 4
- rank_change: unavailable
- category: Home & Kitchen
- theme: home_and_living
- price: CNY 67.08
- rating: 4.5
- review_count: 165
- ASIN: B0GYYFY9B5
- url: https://www.amazon.com/dp/B0GYYFY9B5

### 4. GORILLA GRIP Stainless Steel Manual Can Opener

- source_list: New Releases
- rank: 5
- rank_change: unavailable
- category: Home & Kitchen
- theme: tools_and_edc
- price: CNY 67.08
- rating: 4.4
- review_count: 6,875
- ASIN: B0GH9R927H
- url: https://www.amazon.com/dp/B0GH9R927H

### 5. Grtard 12 Pack Magnetic Clips

- source_list: New Releases
- rank: 6
- rank_change: unavailable
- category: Home & Kitchen
- theme: storage_and_organization
- price: CNY 53.71
- rating: 4.6
- review_count: 12,699
- ASIN: B0GVNJDLR3
- url: https://www.amazon.com/dp/B0GVNJDLR3

### 6. WEIZE 10x10 Pop Up Canopy Tent

- source_list: New Releases
- rank: 10
- rank_change: unavailable
- category: Home & Kitchen
- theme: outdoor_accessories
- price: CNY 537.68
- rating: 4.3
- review_count: 556
- ASIN: B0GYRTDSL1
- url: https://www.amazon.com/dp/B0GYRTDSL1

### 7. 12 Pack 3D Dragonfly Clips

- source_list: New Releases
- rank: 13
- rank_change: unavailable
- category: Home & Kitchen
- theme: outdoor_accessories
- price: unavailable
- rating: 4.4
- review_count: 1,203
- ASIN: B0H3HHXFSW
- url: https://www.amazon.com/dp/B0H3HHXFSW

### 8. Refill Cartridges, 10 Pack 2026 Upgraded Refills

- source_list: New Releases
- rank: 16
- rank_change: unavailable
- category: Home & Kitchen
- theme: cleaning
- price: unavailable
- rating: 4.5
- review_count: 165
- ASIN: B0GXQ22VWW
- url: https://www.amazon.com/dp/B0GXQ22VWW

### 9. WEERSHUN Travel Pillow for Airplanes

- source_list: New Releases
- rank: 19
- rank_change: unavailable
- category: Home & Kitchen
- theme: travel_accessories
- price: CNY 268.81
- rating: 4.5
- review_count: 120
- ASIN: B0H8NDYZBP
- url: https://www.amazon.com/dp/B0H8NDYZBP

### 10. Frost Buddy Togo Buddy 30oz Tumbler

- source_list: New Releases
- rank: 20
- rank_change: unavailable
- category: Home & Kitchen
- theme: travel_accessories
- price: CNY 268.81
- rating: 4.6
- review_count: 3,318
- ASIN: B0H6JWDY5D
- url: https://www.amazon.com/dp/B0H6JWDY5D

### 11. OLANLY Microfiber Bathroom Rug 30x20

- source_list: New Releases
- rank: 22
- rank_change: unavailable
- category: Home & Kitchen
- theme: home_and_living
- price: CNY 67.15
- rating: 4.3
- review_count: 49
- ASIN: B0H3662D3Z
- url: https://www.amazon.com/dp/B0H3662D3Z

### 12. STANLEY Assembly Lunch Box 3.5L

- source_list: New Releases
- rank: 24
- rank_change: unavailable
- category: Home & Kitchen
- theme: bags_and_carry
- price: CNY 168.05
- rating: 4.6
- review_count: 42
- ASIN: B0H4P1GTFT
- url: https://www.amazon.com/dp/B0H4P1GTFT

### 13. DicraoLea 6-pack 16 oz Overnight Oats Containers with Lids

- source_list: New Releases
- rank: 25
- rank_change: unavailable
- category: Home & Kitchen
- theme: storage_and_organization
- price: CNY 96.06
- rating: 4.8
- review_count: 322
- ASIN: B0H6DGPMD8
- url: https://www.amazon.com/dp/B0H6DGPMD8

## 6. Key Questions

### 1. Can Movers & Shakers stably provide products that are rapidly growing?

Not in this probe. Its public title explicitly describes 24-hour sales-rank gainers, but the tested response did not expose a usable product grid, rank changes, or growth percentages. The trend meaning is clear; stable item extraction was not demonstrated.

### 2. Can New Releases stably provide newly appearing products with early market feedback?

Partially yes. The tested page exposed 30 ranked items with ASINs and images, 29 with ratings and review counts, and 24 with prices. It identifies best-selling new and future releases, but the probe did not verify listing dates, and review counts may include variation-level history rather than feedback collected only after the new release.

### 3. What percentage of the sample is simple physical merchandise?

13 of 30, or 43.3%.

### 4. Does Amazon add directions beyond Reddit, Kickstarter, and Yanko?

Within this Home & Kitchen sample, yes at a moderate level: the simple products covered home, outdoor, travel, storage, cleaning, bags, and a manual kitchen tool. The probe did not demonstrate pet, office, apparel, or hobby coverage because no additional categories were requested after reaching the 30-item limit.

### 5. Is a formal Amazon scraper warranted?

REVIEW. New Releases has useful consumer-product fields and a 43.3% simple-product rate, but Movers & Shakers extraction was not demonstrated, price and review fields were incomplete, public-page structure is presentation-oriented, and automated access showed inconsistent responses across retrieval methods.

## 7. Conclusion

- Amazon Movers & Shakers: PARTIAL
- Amazon New Releases: AVAILABLE
- Authentication Required: NO
- Simple Physical Relevance: MEDIUM
- Category Diversity: MEDIUM
- Trend Signal Quality: MEDIUM
- Automation Stability: LOW
- Recommended for Product Picker: REVIEW

The New Releases page is a useful low-cost discovery probe for mature consumer products. The stronger rapid-growth source, Movers & Shakers, did not expose stable item data in this test, so Amazon's complete consumer-trend role is not yet validated.
