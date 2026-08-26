# Creative Product Source Probe

Probe date: 2026-08-25

Scope: low-volume, read-only access testing of public endpoints. No login, access-control bypass, AI classification, database write, pipeline run or formal scraper was used. Ten recent RSS records per source were parsed with simple keyword/manual rules.

## 1. Yanko Design

### Public Entry Points

| Entry point | Result |
| --- | --- |
| RSS: `https://www.yankodesign.com/feed/` | HTTP 200, `application/rss+xml`; 10 recent items parsed |
| Sitemap index: `https://www.yankodesign.com/sitemap_index.xml` | HTTP 200 after redirect to `https://www.yankodesign.com/sitemap.xml`; XML available |
| Guessed product category: `https://www.yankodesign.com/category/product-design/` | HTTP 404; not a usable category endpoint in this probe |
| Public article HTML | HTTP 200 on the sampled article |
| Article JSON-LD | Present: 2 JSON-LD blocks; sampled `WebPage` record exposed `description` and `datePublished` |
| OpenGraph/meta | Sample exposed `og:title`, `og:description`, `og:image` and `article:published_time` |

### Field Availability

| Field | Availability | Observed source |
| --- | --- | --- |
| title | Stable | RSS `<title>` |
| description/excerpt | Stable | RSS `<description>`; article meta also present |
| url | Stable | RSS `<link>` |
| published_at | Stable | RSS `<pubDate>`; article meta/JSON-LD also present |
| category/tags | Stable | Multiple RSS `<category>` elements |
| image_url | Available with article request | `og:image`; no dedicated RSS media/enclosure URL was found in the 10 parsed items |
| headline | Partial | Sampled JSON-LD did not expose a distinct `headline`; OpenGraph title was present |
| JSON-LD description | Available | Sampled `WebPage` record |
| JSON-LD datePublished | Available | Sampled `WebPage` record |
| JSON-LD keywords/category | Not observed | Not present in the sampled JSON-LD record; RSS categories were available |

### Recent Sample (10)

#### 1. The Cassette Revival Has Had a Player Problem, and FiiO Just Fixed It

- description: Vinyl already had its big cultural moment, dragging turntables and record stores back into the mainstream. Cassette tapes…
- category: Audio, Gadgets, Music, Technology, cassette player, Fiio, Retro
- content_type: physical_product
- published_at: Tue, 25 Aug 2026 08:15:51 +0000
- url: https://www.yankodesign.com/2026/08/25/the-cassette-revival-has-had-a-player-problem-and-fiio-just-fixed-it/

#### 2. Full-Color 3D Printing Once Cost $50,000+, HeyGears Brings It to 10% of the Cost

- description: True full-color 3D printing has always been costly; this article covers a lower-cost full-color printer.
- category: Appliances, Deals, Product Design, Technology, 3D printer, 3D printing, Shop
- content_type: technology
- published_at: Tue, 25 Aug 2026 01:45:57 +0000
- url: https://www.yankodesign.com/2026/08/24/full-color-3d-printing-once-cost-50000-heygears-brings-it-to-10-of-the-cost/

#### 3. Someone Finally Built the Three’s Company Apartment in LEGO, Celebrating the 70s Sitcom

- description: A LEGO interpretation of the apartment from the 1970s sitcom Three’s Company, presented through LEGO Ideas.
- category: Toys, LEGO, LEGO Ideas
- content_type: concept_design
- published_at: Tue, 25 Aug 2026 00:30:19 +0000
- url: https://www.yankodesign.com/2026/08/24/someone-finally-built-the-threes-company-apartment-in-lego-celebrating-the-70s-sitcom/

#### 4. This Desk Lamp Finally Solved the Cord Problem Every Remote Worker Just Accepts

- description: A desk lamp design addressing cord placement and the way lighting is positioned in a remote-work setting.
- category: Deals, Lighting, Shop, Lamp, lamp design, YD Select
- content_type: physical_product
- published_at: Mon, 24 Aug 2026 23:30:07 +0000
- url: https://www.yankodesign.com/2026/08/24/this-desk-lamp-finally-solved-the-cord-problem-every-remote-worker-just-accepts/

#### 5. This Award-Winning Armchair Proves One Bold Detail Changes Everything

- description: Pepê Lima’s Jacob armchair uses a prominent visual detail as the central element of its furniture design.
- category: Furniture, Product Design, Armchair, European Product Design Award
- content_type: physical_product
- published_at: Mon, 24 Aug 2026 22:30:31 +0000
- url: https://www.yankodesign.com/2026/08/24/this-award-winning-armchair-proves-one-bold-detail-changes-everything/

#### 6. Apple Watch Ultra 4 May Finally Add Touch ID This September, Along With A Thinner Case

- description: Product news about a possible thinner Apple Watch Ultra case and the potential addition of fingerprint recognition.
- category: News, Product Design, Watches, Wearables, Apple, Watch Ultra
- content_type: technology
- published_at: Mon, 24 Aug 2026 21:30:47 +0000
- url: https://www.yankodesign.com/2026/08/24/apple-watch-ultra-4-may-finally-add-touch-id-this-september-along-with-a-thinner-case/

#### 7. Forget the Movie: AMC’s Hello Kitty Backpack Steals the Show

- description: A Hello Kitty-themed backpack associated with an AMC movie release and intended as a wearable consumer item.
- category: Fashion, Backpack, Hello Kitty, theater
- content_type: physical_product
- published_at: Mon, 24 Aug 2026 20:30:36 +0000
- url: https://www.yankodesign.com/2026/08/24/forget-the-movie-amcs-hello-kitty-backpack-steals-the-show/

#### 8. SylvanSport VIRE packs king-size bed, wet bath, and full kitchen into 19.5-foot trailer

- description: A 19.5-foot camper trailer combining a king-size bed, wet bath and full kitchen in an aerodynamic package.
- category: Automotive, Outdoor, Camper trailer
- content_type: vehicle
- published_at: Mon, 24 Aug 2026 19:15:05 +0000
- url: https://www.yankodesign.com/2026/08/24/sylvansport-vire-packs-king-size-bed-wet-bath-and-full-kitchen-into-19-5-foot-trailer/

#### 9. CMF Clip Pro Review: More Than Just a Pretty Case

- description: A review of open-ear wireless earbuds, their case and their practical audio-product characteristics.
- category: Accessories, Audio, Reviews, Technology, CMF, earbuds, Nothing, TWS Earbuds, wireless earbuds
- content_type: technology
- published_at: Mon, 24 Aug 2026 15:20:00 +0000
- url: https://www.yankodesign.com/2026/08/24/cmf-clip-pro-review-more-than-just-a-pretty-case/

#### 10. Arcade2TV-XR MAX is a 3-in-1 gaming machine tailored for enjoying arcade and pinball in immersive VR spaces

- description: A three-in-one gaming machine for arcade, pinball and immersive virtual-reality use.
- category: Gadgets, Gaming, arcade, game controller, gaming, VR
- content_type: technology
- published_at: Mon, 24 Aug 2026 14:20:30 +0000
- url: https://www.yankodesign.com/2026/08/24/arcade2tv-xr-max-is-a-3-in-1-gaming-machine-tailored-for-enjoying-arcade-and-pinball-in-immersive-vr-spaces/

### Probe Conclusion

- Access: AVAILABLE
- Best Access Method: RSS
- Physical Product Relevance: HIGH
- Recommended for Product Picker: YES

The 10-item sample contained 4 `physical_product`, 4 `technology`, 1 `concept_design` and 1 `vehicle` record. RSS supplied the core fields consistently; one article request supplied the public image and additional metadata.

## 2. Designboom

### Public Entry Points

| Entry point | Result |
| --- | --- |
| RSS: `https://www.designboom.com/feed/` | HTTP 200, `application/rss+xml`; 10 recent items parsed |
| Design page: `https://www.designboom.com/design/` | HTTP 200, public HTML available |
| Sitemap index: `https://www.designboom.com/sitemap_index.xml` | Timed out during the single direct probe; not relied on |
| Public article HTML | HTTP 200 on the sampled article |
| Article JSON-LD | No `application/ld+json` block observed on the sampled article |
| OpenGraph/meta | Sample exposed `og:title`, `og:image`, `description` and `article:published_time`; `og:description` was blank |

### Field Availability

| Field | Availability | Observed source |
| --- | --- | --- |
| title | Stable | RSS `<title>` |
| description/excerpt | Stable | RSS `<description>` |
| url | Stable | RSS `<link>` |
| published_at | Stable | RSS `<pubDate>`; article meta also present |
| category/tags | Stable | Multiple RSS `<category>` elements |
| image_url | Stable | RSS media URL; article `og:image` also present |
| headline | Not observed in JSON-LD | OpenGraph title was available |
| JSON-LD description | Not observed | No JSON-LD block in the sampled article |
| JSON-LD datePublished | Not observed | Article meta supplied the publication timestamp |
| JSON-LD keywords/category | Not observed | RSS categories were available |

### Recent Sample (10)

#### 1. sordo madaleno sinks open-air art gallery four meters below ground in los cabos

- description: A sloping ramp drops visitors four meters below Ánima Village into an open-air gallery framed by concrete and desert.
- category: architecture, architecture in mexico, museums and galleries, sordo madaleno arquitectos
- content_type: architecture
- published_at: Tue, 25 Aug 2026 02:10:09 +0000
- url: https://www.designboom.com/architecture/sordo-madaleno-art-gallery-los-cabos-arte-abierto-baja-anima-village-mexico/

#### 2. cool blue tones meet a vivid red counter inside hubarch’s new optics boutique

- description: Pale blue interiors, polished concrete and a custom red counter shape an optics boutique through restrained color contrast.
- category: design, interiors, readers, architecture in russia, retail interiors
- content_type: architecture
- published_at: Mon, 24 Aug 2026 22:50:36 +0000
- url: https://www.designboom.com/readers/cool-blue-tones-meet-a-vivid-red-counter-inside-hubarchs-new-optics-boutique/

#### 3. S+DLH and VASTO gallery bring contemporary art and collectible design under one roof

- description: A gallery project combines contemporary art, collectible design and interior space through a shared material language.
- category: art, readers, ceramic art and design, furniture design, materials, museums and galleries, sculpture
- content_type: other
- published_at: Mon, 24 Aug 2026 22:26:28 +0000
- url: https://www.designboom.com/art/sierra-de-la-higuera-vasto-gallery-art-collectible-design-one-roof/

#### 4. biosphere 2: what happens when humans try to recreate earth?

- description: A closed-loop living experiment highlights relationships among ecosystems, infrastructure and human habitation.
- category: architecture, architecture in the US, MODES OF HABITATION
- content_type: architecture
- published_at: Mon, 24 Aug 2026 20:35:19 +0000
- url: https://www.designboom.com/architecture/biosphere-2-humans-earth/

#### 5. wittman estes revisits le corbusier’s ‘minimum cell’ with floating pacific northwest cabin

- description: A 40-square-meter guest house applies minimum-cell logic to a remote forest site in Washington State.
- category: architecture, interiors, architecture in the US, architecture on stilts, cabin architecture and design
- content_type: architecture
- published_at: Mon, 24 Aug 2026 18:10:48 +0000
- url: https://www.designboom.com/architecture/wittman-estes-corbusier-minimum-cell-cabin-blakely-island-washington/

#### 6. jae k kim’s timbercraft book rediscovers traditional east asian wooden construction

- description: A book connects traditional East Asian timber joinery with contemporary architectural design.
- category: newsletter inclusion, readers, video
- content_type: other
- published_at: Mon, 24 Aug 2026 14:14:26 +0000
- url: https://www.designboom.com/readers/jae-k-kims-timbercraft-book-rediscovers-traditional-east-asian-wooden-construction/

#### 7. ann veronica janssens fills Hermès ginza with light, fog and shifting perception

- description: An exhibition uses heat-sensitive swings and colored-light clouds to alter the perception of an architectural space.
- category: art, exhibitions, Hermès, interactive installation
- content_type: other
- published_at: Mon, 24 Aug 2026 09:35:32 +0000
- url: https://www.designboom.com/art/ann-veronica-janssens-hermes-ginza-exhibition-light-fog/

#### 8. 3D printed standalone alarm clock lets you smash a giant arcade button to wake up

- description: A standalone alarm clock combines programmable alarms, mechanical controls, removable electronics and a large button.
- category: technology, video, 3D printing, personal technology
- content_type: physical_product
- published_at: Mon, 24 Aug 2026 07:45:16 +0000
- url: https://www.designboom.com/technology/3d-printed-standalone-alarm-clock-giant-arcade-button-endothermal-systems-cinderclock/

#### 9. pyramids and maya forms shape coco brun and sten studio’s stone vessels

- description: Limited-edition vessels use upcycled travertine, marble and onyx with forms inspired by pyramids and Maya references.
- category: design, readers, marble and stone design, recycling, sculpture
- content_type: physical_product
- published_at: Mon, 24 Aug 2026 07:13:11 +0000
- url: https://www.designboom.com/design/pyramids-and-maya-forms-shape-coco-brun-and-sten-studios-stone-vessels/

#### 10. sonos syncs entire home acoustics with multi channel amplifier

- description: A multi-channel amplifier coordinates sound across home architectural spaces for a unified audio experience.
- category: technology, SONOS, sound art
- content_type: technology
- published_at: Mon, 24 Aug 2026 07:00:57 +0000
- url: https://www.designboom.com/technology/sonos-amp-multi-syncs-entire-home-acoustics/

### Probe Conclusion

- Access: AVAILABLE
- Best Access Method: RSS
- Physical Product Relevance: LOW
- Recommended for Product Picker: REVIEW

The 10-item general-feed sample contained 2 `physical_product`, 4 `architecture`, 3 `other` and 1 `technology` record. Public RSS fields were consistent, but the general feed was dominated by architecture, interiors and art; the public Design page can serve as a narrower entry point if investigated later.
