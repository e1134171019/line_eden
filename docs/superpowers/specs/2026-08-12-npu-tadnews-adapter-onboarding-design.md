# NPU + Tadnews Adapter Onboarding Design

## Goal

Reduce high-noise generic-anchor parsing for two verified scholarship sources without introducing paid services, AI collection dependencies, or universal DOM assumptions.

This batch targets:

- `npu-scholarship-portal` — 國立澎湖科技大學獎助學金公告
- `nchu-external-scholarships` — 國立中興大學校外獎助學金

## Context and Baselines

Final source-health evidence from Scholarship Source Contract #167:

- NPU: collected 98; raw/parsed/rejected = `1725/98/1627`; 10/10 pages succeeded.
- NCHU: collected 30; raw/parsed/rejected = `482/30/452`; 2/2 pages succeeded even though the live Tadnews list exposes more pages.

The generic collector counts every anchor in page chrome as a raw row and then filters by scholarship markers. That preserves recall but creates very high rejection ratios and, for NCHU, under-discovers pagination.

## Live Structural Evidence

### NPU

Verified public structure:

- Listing entry: `/sub/latestevent/index.aspx?Parser=9,22,501,486...`
- Listing rows are scholarship announcements with an adjacent publication date.
- Detail URLs use the same host and `/sub/latestevent/Details.aspx?Parser=...` path.
- The list exposes explicit multi-page navigation and detail pages carry `公布日期`.

The adapter must accept only same-host `/sub/latestevent/Details.aspx` detail URLs whose query contains a non-empty `Parser` value. Path and query-key comparisons are case-insensitive; query values are not rewritten.

### NCHU Tadnews

Verified public structure:

- Listing: `/osa/laa/sys/modules/tadnews/index.php?ncsn=4`
- Pagination: same path with `g2p=<page>` and the same `ncsn=4` category.
- Detail: same path with `ncsn=4&nsn=<id>`.
- Each list item includes publication date, category marker `校外獎助學金`, application route marker, and title.

The adapter must accept only same-host Tadnews `index.php` detail URLs under a `/modules/tadnews/` path with a numeric `nsn` and preserve the configured `ncsn` category. Pagination support must recognize `g2p` as Tadnews's page query key.

## Design

### 1. `NPU_LATESTEVENT_LIST`

Add a narrow collector that subclasses `AdditionalScholarshipSourceCollector` and overrides `_parse_html`.

Contract:

- Only same-host `/sub/latestevent/Details.aspx` links are candidates.
- Candidate URL must contain a non-empty `Parser` query value.
- Title comes from the detail anchor / row context, excluding generic navigation labels.
- Publication date comes from the listing row's independent date text, not deadline text embedded in the title.
- `raw_rows` counts only URL-contract candidates, not all page anchors.

No custom HTTP layer and no new pagination engine are added; the existing `crawl_listing_pages` remains the runner.

### 2. `TADNEWS_CATEGORY_LIST`

Add a narrow collector for Tadnews category listings.

Contract:

- Only same-host `/modules/tadnews/index.php` URLs with numeric `nsn` are detail candidates.
- If the configured entry has `ncsn`, candidate detail URLs must preserve the same `ncsn`.
- `raw_rows` counts only matching Tadnews detail candidates.
- Publication date is extracted from the containing list/article context, excluding the title text when necessary.

Pagination:

- Extend the existing safe numbered-page recognizer to treat `g2p` as a page query key.
- Existing host/path equality rules remain unchanged, so `g2p` cannot navigate off-site or outside the listing path family.

### 3. Production mappings

Only these mappings change in this batch:

- `npu-scholarship-portal` → `NPU_LATESTEVENT_LIST`
- `nchu-external-scholarships` → `TADNEWS_CATEGORY_LIST`

No other additional source changes adapter ID or URL.

## Alternatives Considered

### Universal page-chrome cleaner

Rejected. A generic DOM cleaner would encode layout guesses across heterogeneous sites and recreate the universal-scraper problem the adapter registry was introduced to remove.

### Canonical URL migration only

Not sufficient for NPU or NCHU. Both entries are already semantically correct source pages; the problem is structural parsing and, for NCHU, pagination discovery.

### One dedicated collector per source without reusable contracts

Safer in the short term but unnecessary here. Both sites expose stable, named URL protocols. The adapters stay narrow enough to be independently testable and reusable only when another source proves the same contract.

## Error Handling and Safety

- Unknown adapter IDs continue to fail closed.
- No SSL verification changes.
- No paid service, AI parser, Gemini, LINE, eligibility, persistence, or entity-resolution changes.
- If live source evidence drops below baseline collected count, rollback only the failing mapping.
- Parser hygiene is accepted only when `rejected_rows` drops by at least 50% from the source baseline; a lower rejection count never compensates for a collected-count regression.

## TDD and Acceptance

Required RED/GREEN sequence:

1. NPU parser module missing → RED; implement parser → GREEN.
2. Tadnews parser module / `g2p` support missing → RED; implement → GREEN.
3. Adapter enum/factory members missing → RED; register → GREEN.
4. Production mapping assertions fail → RED; switch only NPU/NCHU → GREEN.
5. Full Quality workflow on Python 3.11 and 3.13.
6. Scholarship Source Contract and 38-program Live Source Contract.

Live acceptance:

- NPU: collected count `>= 98`; rejected rows `<= 813` (at least 50% lower than baseline 1627).
- NCHU: collected count `>= 30`; rejected rows `<= 226` (at least 50% lower than baseline 452). If the live Tadnews page still exposes more than 2 pages at verification time, `pages_detected` must be `> 2`.
- For both sources, zero parser/fetch errors attributable to the new adapter are required.
- Roll back each mapping independently if any source-specific criterion fails.

## Explicit Holds

Not part of this batch:

- NFU: a better scholarship-specific official page was found, but its canonical migration will be a separate batch so its URL-change risk is isolated.
- TP2E: WordPress archive mixes activities, awards, and sidebar permalinks; existing `WORDPRESS_ARCHIVE` remains unassigned until a safe main-loop contract is verified.
- 潘文淵: lower current noise and lower priority than NPU/NCHU.

## Production Acceptance #85

The final prior-head Production Acceptance failure is not attributed to collector behavior. Full source collection and 178 semantic checks completed; enforcement failed because the private `profile.json` lacked nationality and enrollment-status fields required to force one known program to `eligible + apply_candidate`. This batch does not modify private profile secrets or eligibility fail-closed behavior.
