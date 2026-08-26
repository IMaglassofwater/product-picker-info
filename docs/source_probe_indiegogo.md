# Indiegogo Official Public API Probe

Probe date: 2026-08-25

This was a low-volume, read-only probe. It used only Indiegogo's documented public API, made no authenticated request, opened no project pages, invoked no AI, and did not change the database, Candidate Pool, Pipeline, scraper code, or scoring rules.

## 1. Official Endpoint

- Documentation: https://help.indiegogo.com/article/616-indiegogo-public-api
- Endpoint: `GET https://www.indiegogo.com/api/public/projects/getActiveCrowdfundingProjects`
- HTTP status: 200
- Response content type: `application/json; charset=utf-8`
- Authentication supplied: none
- Active projects returned by the endpoint: 288
- Records inspected: first 30 only
- Ordering documented by Indiegogo: campaign start date

## 2. Access Result

- Access: AVAILABLE
- Official API: YES
- Authentication Required: NO
- Best Access Method: Official Public API JSON

The endpoint returned a JSON array without an API key, cookie, account, or login. No pagination, project-page requests, or non-public endpoint was attempted.

## 3. Field Availability

| Field | Present and non-null | Quality note |
| --- | ---: | --- |
| projectName | 30 / 30 | Stable string |
| shortDescription | 30 / 30 | Stable string; detail level varies |
| projectHomeUrl | 30 / 30 | Stable public project URL |
| projectImageUrl | 30 / 30 | Stable public image URL |
| backerCount | 30 / 30 | Numeric |
| campaignGoal | 28 / 30 | Numeric when present; 2 records had no usable positive goal |
| fundsGathered | 30 / 30 | Numeric |
| currencyShortName | 30 / 30 | Stable currency code |
| campaignStartDate | 30 / 30 | ISO timestamp |
| campaignEndDate | 30 / 30 | ISO timestamp |
| creatorName | 30 / 30 | Stable string |
| commentCount | 30 / 30 | Numeric |

Funding percentage was calculated locally only when `campaignGoal > 0`:

`funding_percentage = fundsGathered / campaignGoal * 100`

Fields Quality: HIGH. Eleven requested fields were complete in all 30 records; `campaignGoal` was usable in 28.

## 4. Probe-only Content Classification

Classification used only project names and short descriptions with fixed rules. It did not call the existing feasibility pipeline or modify any score.

| Content type | Count |
| --- | ---: |
| physical_product | 5 |
| software | 3 |
| complex_technology | 5 |
| other | 17 |
| Total | 30 |

The `other` group includes films, music releases or tours, live productions, venue/business fundraising, and projects that are not a discrete product. AI services and websites were marked `software`; connected devices, machinery, smart hardware and electric mobility were marked `complex_technology`.

### Physical-product feasibility check

| Probe label | Count |
| --- | ---: |
| potentially_feasible | 3 |
| hardcore_or_complex | 0 |
| uncertain | 2 |

This label is an audit-only description of the sample. It is not a Candidate Pool decision or feasibility score.

## 5. Theme Distribution

Each of the 30 projects received one primary probe theme.

| Theme | Count |
| --- | ---: |
| bags_and_carry | 1 |
| storage_and_organization | 0 |
| travel_accessories | 0 |
| desk_and_office | 0 |
| outdoor_accessories | 0 |
| home_and_living | 1 |
| pet_accessories | 0 |
| apparel_accessories | 2 |
| tools_and_edc | 0 |
| electronics | 5 |
| other | 21 |
| Total | 30 |

The sample was not concentrated in bags_and_carry, but 21 of 30 records fell into `other` rather than a Product Picker consumer-product theme. The observed diversity therefore came mainly from non-product campaigns, not from a broad set of simple physical products.

## 6. Market Validation Distribution

### funding_percentage

| Range | Count |
| --- | ---: |
| <50% | 27 |
| 50–99% | 0 |
| 100–299% | 1 |
| 300–999% | 0 |
| >=1000% | 0 |
| Not calculable because campaignGoal was not positive | 2 |

### backerCount

| Range | Count |
| --- | ---: |
| 0–49 | 30 |
| 50–199 | 0 |
| 200–999 | 0 |
| >=1000 | 0 |

The endpoint is ordered by campaign start date, so this first-30 sample represents newly active campaigns rather than the most-funded campaigns.

## 7. Top Physical Product / Potentially Feasible Samples

Only 3 of the first 30 records met the probe's `physical_product / potentially_feasible` label, so all 3 are shown.

### 1. 5 in 1 Convertible Jacket, Backpack, Pillow, Holder, Utility

- description: Insert Jacket(s) into Jacket, Backpack mode, Pillow mode, Replaces Bags with huge pouch, Utility type, 8 pockets, Wind and Water resistant…
- theme: bags_and_carry
- funding_percentage: 110.60%
- backerCount: 2
- campaignGoal: 500 USD
- fundsGathered: 553 USD
- url: https://www.indiegogo.com/projects/krideas/5-in-1-convertible-jacket-backpack-pillow-holder-utility

### 2. Vampiglet 3: Spooky Colored Fun Special

- description: Vampiglet issue 3 is a gothic extravaganza of spooky colored fun for mature readers; this third issue continues the publication.
- theme: other
- funding_percentage: 48.09%
- backerCount: 5
- campaignGoal: 500 USD
- fundsGathered: 240.45 USD
- url: https://www.indiegogo.com/projects/big-bidniz-studios/vampiglet-3-spooky-colored-fun-special

### 3. Towel Design Matters

- description: Certified by the Japan Textile Inspection Association and made from 70% bamboo and 30% cotton fibers for softness and absorbency.
- theme: home_and_living
- funding_percentage: unavailable because campaignGoal was not positive
- backerCount: 0
- campaignGoal: unavailable
- fundsGathered: 0 CAD
- url: https://www.indiegogo.com/projects/pdmbrand/towl-design-matters

## 8. Data Quality and Relevance Conclusion

- Indiegogo Access: AVAILABLE
- Official API: YES
- Authentication Required: NO
- Fields Quality: HIGH
- Physical Product Relevance: LOW
- Simple Product Relevance: LOW
- Candidate Diversity Value: LOW
- Recommended for Product Picker: REVIEW

The official endpoint is inexpensive to consume and exposes the requested market-validation fields directly. In the first 30 records, however, only 5 were physical products and only 3 were potentially simple; all 30 had fewer than 50 backers, and 21 belonged to the `other` theme. The endpoint is technically suitable, while the unfiltered newest-project sample has low immediate relevance to the current Product Picker scope.
