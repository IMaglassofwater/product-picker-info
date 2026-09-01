# Phase 11E Evidence-First Source Validation

Date: 2026-08-31

This was a bounded local/source validation. It did not write to production Neon,
call Gemini or WxPusher, switch the production UI, commit, or push.

## Source Results

| Source | Access | Public method | Fetched | Observed | Eligible | Concrete | Daily families | Limitation |
|---|---|---|---:|---:|---:|---:|---:|---|
| Etsy | BLOCKED | Official Etsy Open API v3 active listings | 0 | 0 | 0 | 0 | 0 | Configured credential names were present, but the bounded HTTPS request timed out. No credential was printed. |
| Hacker News / Show HN | AVAILABLE | Official Hacker News Firebase API (`showstories` + `item`) | 30 | 30 | 24 | 24 | 24 | No comment text was fetched; only source-native points/comment counts/timestamp/author/URLs were retained. |
| Software Reddit | BLOCKED | Public subreddit RSS | 0 | 0 | 0 | 0 | 0 | The bounded r/SideProject RSS probe timed out. No authenticated or anti-bot workaround was attempted. |
| Design Milk | PROBE_ONLY / BLOCKED | Public RSS advertised by Design Milk | 0 | 0 | 0 | 0 | 0 | FeedBurner timed out; the direct `/feed/` endpoint returned HTTP 403. No page scraping was attempted. |

The Show HN controlled run used a temporary SQLite database and the real path:
Observation → Eligibility → Concrete Product Gate → Product Identity → Product
Family → Evidence → Daily Discovery. All 24 qualifying families remained visible,
including weak-evidence records; Candidate/Gemini/Qualified was not consulted.

### Show HN Type and Evidence Distribution

- Physical: 1
- Software: 23
- Product Design: 0
- Evidence Weak: 16
- Evidence Moderate: 6
- Evidence Strong: 2
- Actual feedback text available: no

## Quality Samples

The following 20 bounded-run examples show the preserved source title and the
deterministic normalized identity. Evidence is limited to the source-native HN
points, comment count, submission timestamp, author, HN URL and external URL.

| Source title | Normalized product name | Type | URL |
|---|---|---|---|
| Show HN: ScoutLayer — a simple API to find contacts from a domain | ScoutLayer | Software | https://news.ycombinator.com/item?id=49504899 |
| Show HN: Prove your code produced your claims without making reviewers rerun it | Prove your code produced your claims without making reviewers rerun it | Software | https://news.ycombinator.com/item?id=49505043 |
| Show HN: NFC Energy-Harvesting PCB Business Card with an MCU | NFC Energy-Harvesting PCB Business Card with an MCU | Physical | https://news.ycombinator.com/item?id=49478426 |
| Show HN: Card Shop Directory — Find trading card shops by state, city, and game | Card Shop Directory | Software | https://news.ycombinator.com/item?id=49504965 |
| Show HN: I missed the moving blocks, so I built a real Linux disk defragmenter | I missed the moving blocks, so I built a real Linux disk defragmenter | Software | https://news.ycombinator.com/item?id=49438865 |
| Show HN: Hillock: Local neuro-symbolic memory engine in less than 1.2GB VRAM | Hillock | Software | https://news.ycombinator.com/item?id=49501209 |
| Show HN: Typebase — A single-folder back end you write in TypeScript | Typebase | Software | https://news.ycombinator.com/item?id=49447178 |
| Show HN: Break 5, the addictive, free 5 minute, daily word game | Break 5, the addictive, free 5 minute, daily word game | Software | https://news.ycombinator.com/item?id=49504150 |
| Show HN: Galaxium, an experimental WebGPU space explorer | Galaxium, an experimental WebGPU space explorer | Software | https://news.ycombinator.com/item?id=49420524 |
| Show HN: Cogram Studio — CAD and BIM workspace for humans and agents | Cogram Studio | Software | https://news.ycombinator.com/item?id=49501620 |
| Show HN: Drop a SQL schema, get an interactive ER diagram | Drop a SQL schema, get an interactive ER diagram | Software | https://news.ycombinator.com/item?id=49497500 |
| Show HN: Bolnee-Chat — Self Hosted Chatbot Integration in Your Business Website | Bolnee-Chat | Software | https://news.ycombinator.com/item?id=49497227 |
| Show HN: SubSmith — Turn your own videos into language-learning material | SubSmith | Software | https://news.ycombinator.com/item?id=49476894 |
| Show HN: Snaketron — Competitive multiplayer Snake | Snaketron | Software | https://news.ycombinator.com/item?id=49499499 |
| Show HN: Murmell — Collaborative cloud canvas for coding agents | Murmell | Software | https://news.ycombinator.com/item?id=49499167 |
| Show HN: Sesame - a local-first, open-source password manager | Sesame | Software | https://news.ycombinator.com/item?id=49483038 |
| Show HN: My startup-idea scanner scored 500 ideas | My startup-idea scanner scored 500 ideas | Software | https://news.ycombinator.com/item?id=49497779 |
| Show HN: Self-hosted mobile-friendly web UI for Herdr agents | Self-hosted mobile-friendly web UI for Herdr agents | Software | https://news.ycombinator.com/item?id=49497870 |
| Show HN: ShevtoneAudio Orchestrator — Turning MIDI into Full Orchestration | ShevtoneAudio Orchestrator | Software | https://news.ycombinator.com/item?id=49497791 |
| Show HN: 1endpoint — Cheaper access to AI models | 1endpoint | Software | https://news.ycombinator.com/item?id=49497665 |

## Excluded Samples (all available in the bounded sample)

| Source title | Eligibility | Concrete | Reason |
|---|---|---|---|
| Show HN: BentoPDF, Hyper Compress and Kura | INELIGIBLE | NON_CONCRETE | Multiple independently named products. |
| Show HN: OpenTIE and OpenXWA, Modern Ports of Tie Fighter and X-Wing Alliance | INELIGIBLE | NON_CONCRETE | Multiple independently named products. |
| Show HN: I asked LLMs to choose between popular developer tools | INELIGIBLE | NON_CONCRETE | Generic experiment/editorial, not one launched product. |
| Show HN: What Apple's OS updates silently change in the on-device AI model | INELIGIBLE | NON_CONCRETE | News/research-style link without one product identity. |
| Show HN: The load-bearing vocabulary of Claude | INELIGIBLE | NON_CONCRETE | Essay-style link without one product identity. |
| Show HN: App design that combines Reddit and Gmail for private treelike convos | INELIGIBLE | NON_CONCRETE | Product concept/editorial rather than an independently researchable launch. |

## Audits

- False-negative audit: an initial conservative rule missed named launches with
  an official external product URL. The deterministic rule now accepts that
  factual launch signal; the final bounded sample had no remaining obvious
  false negative among the six exclusions.
- Suspicious-pass audit: four editorial/concept titles initially passed. They
  were moved to explicit non-product rules before final validation.
- Identity audit: delimiter-based Show HN names normalized well; several
  sentence-form titles remain literal rather than being aggressively rewritten.
- Family safety: 24 singleton families, zero multi-record families, zero
  multi-source families and no observed over-merge. False splits remain
  intentionally preferable.
- Possible cross-source matches: none in the isolated new-source validation.
- Actual user feedback: unavailable for all four probes; adapters explicitly
  retain `user_feedback_available=false` rather than inventing review claims.

## Existing-Source Regression and Roadmap

Existing Reddit, Amazon, Kickstarter, Indiegogo, Yanko Design and Product Hunt
adapters remain registered. Product Hunt remains an automatically eligible,
concrete software source in Evidence-First Daily Discovery without Gemini.

NEXT / LATER: GitHub product discovery, Core77 access probe, and Designboom
review. The future user-facing cutover remains one persisted Daily Discovery
Dataset feeding both Today UI and WxPusher with content parity; it is not part
of Phase 11E.

## Phase 11E.1 Recovery Validation

Etsy was not called. Its developer status is now documented and enforced as
`DEFERRED_PENDING_PERSONAL_APPROVAL` until the user explicitly enables approved
access.

Software Reddit now subclasses the existing Arctic Shift adapter instead of
maintaining a second RSS transport. The selected communities remain:

- `SideProject`: concrete launches and independently testable side projects.
- `selfhosted`: deployable end-user tools and self-hosted product needs.
- `opensource`: inspectable open-source end-user and developer products.
- `productivity`: concrete workflow utilities and single-product needs.

Arctic Shift's optional query parameter returned HTTP 422 for some community/
query pairs, so the same public endpoint now uses one bounded no-query request
plus one bounded query request per community. Existing intent filtering,
per-community failure isolation, raw Product persistence and Evidence-First
projection remain unchanged.

### Controlled Software Reddit Result

| Subreddit | Fetched | Observed | Eligible | Concrete | Daily families | Software | Failure |
|---|---:|---:|---:|---:|---:|---:|---|
| SideProject | 2 | 2 | 2 | 1 | 1 | 1 | none |
| selfhosted | 7 | 7 | 7 | 4 | 4 | 4 | none |
| opensource | 6 | 6 | 6 | 6 | 6 | 6 | none |
| productivity | 25 | 25 | 21 | 11 | 9 | 11 | none |
| **Total** | **40** | **40** | **36** | **22** | **19** | **22** | **none** |

The difference between 22 concrete records and 19 families is conservative
same-concept grouping (for example screen-time blockers and note-taking apps),
not a Top-N or evidence cutoff. Evidence among the concrete records was 15
WEAK, 6 MODERATE and 1 STRONG. Weak evidence remained visible.

Representative accepted identities:

- `made a screen time app...` → `Screen-Time App Blocker`
- `I’m building a local Minecraft server manager...` → `Self-Hosted Minecraft Server Manager`
- `Looking for a Watch/Read List Order Tracker` → `Watch / Read List Tracker`
- `MindSpark: a self-hostable mind-mapping app...` → `MindSpark Mind-Mapping App`
- `C-Shop - GPU accelerated image editor...` → `C-Shop Image Editor`
- `Testing Files Generator - 100% offline...` → `Testing Files Generator`
- `PULS: Unified System Monitoring...` → `PULS Linux System Monitoring Tool`
- `Vectoria...document exploration workspace` → `Vectoria Document Exploration Workspace`
- `JustForms client-side PDF form editor...` → `JustForms PDF Form Editor`
- `Looking for an app blocker/screen time app` → `Screen-Time App Blocker`
- `I need notetaking app for studying` → `Note-Taking App`
- `Working on...Taskodoro` → `Taskodoro Task Management App`
- `Feedback please - habit tracking...` → `Habit Tracking App`
- `Looking for...digital sticky notes` → `Digital Sticky Notes App`
- `App like the chores app “ourhome”?` → `Household Chores App`

Actual source evidence retained score, comment count, timestamp, author,
subreddit and direct URL. Comment text was unavailable and was not invented.
The audit removed moderator-deleted records before Product creation and caught
13 deterministic suspicious-pass patterns covering troubleshooting,
megathreads, recommendation lists, vague concepts and generic discussions. No
obvious false negative remained in the controlled excluded sample.

### Final Design Milk Probe

The last bounded legitimate probe checked the previously advertised FeedBurner
RSS, WordPress sitemap, sitemap index, product-design tag feed, home-furnishings
category feed and Latest page. FeedBurner timed out and every direct public
endpoint returned HTTP 403. No proxy, fingerprint spoofing, Cloudflare bypass
or aggressive scraping was attempted. `DESIGN_MILK` is therefore `DEFERRED`.

### HN and Identity Regression

A fresh 10-item official Show HN regression produced 7 concrete Daily
Discovery records. External product URLs, points and comment counts were
present, and WEAK evidence records remained visible. Four deterministic
sentence identities were cleaned up:

- `I missed the moving blocks...Linux disk defragmenter` → `Linux Disk Defragmenter`
- `Drop a SQL schema, get an interactive ER diagram` → `Interactive SQL ER Diagram Tool`
- `My startup-idea scanner scored 500 ideas...` → `Startup Idea Scanner`
- `Prove your code produced your claims...` → `Code Claim Verification Tool`

Reddit sentence identities without a safe deterministic rewrite now preserve
the original title with LOW confidence instead of inventing a product name.
